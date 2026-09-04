"""Phase 11 contracts: the /api/v4 model-gateway surface.

Covers the write-only credential contract (the migration matrix test oracle
for ``api.model_gateway``), routing rule management, fail-closed invocation
routing, receipts, and policy enforcement.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from windagent.kernel.ids import ActorId
from windagent.modules.model_gateway.infrastructure.secret_store import (
    CANONICAL_KEY_ENV,
    EncryptedSecretStore,
)
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import metadata
from windagent.platform.security import (
    Authenticator,
    Identity,
    IdentityKind,
    RuleBasedPolicyEngine,
)
from windagent_api.app import create_app

PROVIDERS_URL = "/api/v4/model-gateway/providers"
RULES_URL = "/api/v4/model-gateway/rules"
SECRET = "sk-live-secret-123"


def _encryption_key() -> str:
    return base64.b64encode(b"k" * 32).decode()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def api_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Any]]:
    monkeypatch.setenv(CANONICAL_KEY_ENV, _encryption_key())
    database_path = (tmp_path / "gateway.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    _run(_create())
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        _run(engine.dispose())


def _register_provider(
    client: TestClient, name: str = "openai", **overrides: object
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "base_url": f"https://api.{name}.example/v1",
        "protocol_mode": "openai",
        "credential": {"secret": SECRET, "label": "primary"},
    }
    payload.update(overrides)
    response = client.post(PROVIDERS_URL, json=payload)
    assert response.status_code == 201, response.text
    return cast("dict[str, Any]", response.json())


def _secret_rows(engine: Any) -> list[tuple[str, str]]:
    from windagent.modules.model_gateway.infrastructure.tables import secrets_table

    async def _collect() -> list[tuple[str, str]]:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            rows = (await session.execute(select(secrets_table))).mappings().all()
        return [(str(row["secret_name"]), str(row["ciphertext"])) for row in rows]

    return cast("list[tuple[str, str]]", _run(_collect()))


class TestProviderRegistryContracts:
    def test_register_and_list_providers(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        provider = _register_provider(client)
        assert provider["name"] == "openai"
        assert provider["endpoint_count"] == 1
        assert provider["has_credential"] is True
        listing = client.get(PROVIDERS_URL).json()["providers"]
        assert [p["name"] for p in listing] == ["openai"]

    def test_duplicate_provider_conflicts(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        _register_provider(client)
        response = client.post(
            PROVIDERS_URL,
            json={"name": "openai", "base_url": "https://other.example/v1"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_unknown_provider_is_not_found(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        response = client.get(f"{PROVIDERS_URL}/pv-missing")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_update_provider_never_edits_secrets(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        provider = _register_provider(client)
        response = client.patch(
            f"{PROVIDERS_URL}/{provider['id']}",
            json={"display_name": "OpenAI Cloud", "enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "OpenAI Cloud"
        assert response.json()["has_credential"] is True


class TestWriteOnlyCredentialContract:
    def test_secret_never_appears_in_any_response(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        _register_provider(client)
        for path in (PROVIDERS_URL, f"{RULES_URL}", "/api/v4/model-gateway/receipts"):
            assert SECRET not in client.get(path).text
        provider = client.get(PROVIDERS_URL).json()["providers"][0]
        detail = client.get(f"{PROVIDERS_URL}/{provider['id']}").text
        assert SECRET not in detail
        assert provider["has_credential"] is True

    def test_secret_is_encrypted_at_rest_and_recoverable(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, engine = api_env
        _register_provider(client)
        rows = _secret_rows(engine)
        assert len(rows) == 1
        secret_name, ciphertext = rows[0]
        assert secret_name.startswith("model_gateway/credentials/")
        assert SECRET not in ciphertext
        assert ciphertext.startswith("enc:v1:")

        store = EncryptedSecretStore(
            async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        )
        revealed = _run(store.read(secret_name))
        assert revealed is not None
        assert revealed.reveal() == SECRET

    def test_rotation_bumps_version_and_never_leaks(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, engine = api_env
        provider = _register_provider(client)
        response = client.put(
            f"{PROVIDERS_URL}/{provider['id']}/credential",
            json={"secret": "sk-rotated-456", "label": "rotated"},
        )
        assert response.status_code == 201
        assert response.json()["secret_version"] == 2
        assert "sk-rotated-456" not in response.text
        assert "sk-rotated-456" not in client.get(PROVIDERS_URL).text
        # The rotated ciphertext replaced the single durable secret row.
        rows = _secret_rows(engine)
        assert len(rows) == 1
        assert "sk-rotated-456" not in rows[0][1]

    def test_credential_removal(self, api_env: tuple[TestClient, Any]) -> None:
        client, engine = api_env
        provider = _register_provider(client)
        response = client.delete(f"{PROVIDERS_URL}/{provider['id']}/credential")
        assert response.status_code == 200
        assert response.json()["removed"] is True
        provider_after = client.get(f"{PROVIDERS_URL}/{provider['id']}").json()
        assert provider_after["has_credential"] is False
        assert _secret_rows(engine) == []


class TestRoutingRuleContracts:
    def test_rule_crud_and_version_bump(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        created = client.post(
            RULES_URL,
            json={
                "rule_id": "story-default",
                "canonical_model_id": "windagent/story-default",
            },
        )
        assert created.status_code == 201
        assert created.json()["rule_version"] == 1
        updated = client.post(
            RULES_URL,
            json={
                "rule_id": "story-default",
                "canonical_model_id": "windagent/story-default",
                "priority": 10,
            },
        )
        assert updated.status_code == 201
        assert updated.json()["rule_version"] == 2
        rules = client.get(RULES_URL).json()["rules"]
        assert len(rules) == 1
        deleted = client.delete(f"{RULES_URL}/story-default")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        missing = client.delete(f"{RULES_URL}/story-default")
        assert missing.status_code == 404

    def test_invocation_without_rules_fails_closed(
        self, api_env: tuple[TestClient, Any]
    ) -> None:
        client, _ = api_env
        response = client.post(
            "/api/v4/model-gateway/invocations",
            json={"task_id": "task-1", "scope_id": "session-1", "prompt": "hi"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        receipts = client.get("/api/v4/model-gateway/receipts").json()
        assert receipts == {"receipts": []}


class TestPolicyEnforcement:
    def test_writes_are_denied_by_a_fail_closed_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CANONICAL_KEY_ENV, _encryption_key())
        database_path = (tmp_path / "gateway-policy.db").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

        async def _create() -> None:
            async with engine.begin() as connection:
                await connection.run_sync(metadata.create_all)

        _run(_create())
        settings = Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{database_path}",
            auth_enabled=True,
        )

        class StubAuthenticator:
            async def authenticate(self, token: str) -> Identity:
                return Identity(
                    actor_id=ActorId.new(),
                    kind=IdentityKind.SERVICE,
                    name="contract-test",
                )

        app = create_app(
            settings,
            authenticator=cast(Authenticator, StubAuthenticator()),
            policy_engine=RuleBasedPolicyEngine(rules=()),
        )
        try:
            with TestClient(app) as client:
                anonymous = client.post(
                    PROVIDERS_URL, json={"name": "x", "base_url": "y"}
                )
                assert anonymous.status_code == 401
                denied = client.post(
                    PROVIDERS_URL,
                    json={"name": "x", "base_url": "y"},
                    headers={"Authorization": "Bearer token-1"},
                )
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "forbidden"
        finally:
            _run(engine.dispose())
