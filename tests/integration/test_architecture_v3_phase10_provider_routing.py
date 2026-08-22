from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from windagent_core.contracts.providers.provider_management import ProviderProbeResult
from windagent_providers.management import (
    ProviderAdapterFactory,
    ProviderManagementService,
    ProviderProbeService,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointHealthSampleORM,
    EndpointModelBindingORM,
    ModelRoutingRuleV3ORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    ProviderRoutingAuditV3ORM,
    ProviderVendorORM,
    RouteLockV3ORM,
)
from windagent_storage.repositories.provider_management_repository import (
    SQLProviderManagementRepository,
)
from windagent_storage.security.encryption import decrypt
from windagent_storage.security.encryption import EncryptionKeyMissingError
from windagent_worker.composition.providers import ProviderComposer
from windagent_worker.composition.settings import WorkerRuntimeSettings
from windagent_worker.composition.studio import StudioComposer
from windagent_api.dependencies import (
    get_provider_management_service,
    get_provider_probe_service,
    get_v3_resource_service,
)
from windagent_api.routers.v3.providers import router as providers_router


PHASE10_TABLES = [
    ProviderVendorORM.__table__,
    ProviderCredentialORM.__table__,
    ProviderEndpointORM.__table__,
    CanonicalModelV3ORM.__table__,
    EndpointModelBindingORM.__table__,
    ModelRoutingRuleV3ORM.__table__,
    RouteLockV3ORM.__table__,
    ProviderRoutingAuditV3ORM.__table__,
    EndpointHealthSampleORM.__table__,
]


@pytest.fixture
def provider_db(tmp_path, monkeypatch):
    secret_key = base64.b64encode(b"p" * 32).decode()
    monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", secret_key)
    db_path = tmp_path / "phase10.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(sync_url)
    BaseORM.metadata.create_all(engine, tables=PHASE10_TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield db_path, factory
    engine.dispose()


@pytest.mark.asyncio
async def test_add_probe_discover_rules_worker_route_and_audit(provider_db):
    db_path, factory = provider_db
    session = factory()
    repo = SQLProviderManagementRepository(session)
    management = ProviderManagementService(repo)
    raw_secret = "synthetic-phase10-secret"

    public = management.add_provider(
        vendor_id="openrouter-test",
        name="OpenRouter Test",
        vendor_type="cloud",
        base_url="https://local.test/v1",
        protocol_mode="openai",
        credential_secret=raw_secret,
        endpoint_id="ep-openrouter-test",
        actor="phase10-test",
    )
    assert public["status"] == "unconfigured"
    assert raw_secret not in json.dumps(public)

    credential = session.query(ProviderCredentialORM).one()
    assert credential.secret_ciphertext.startswith("enc:v1:")
    assert raw_secret not in credential.secret_ciphertext
    assert decrypt(credential.secret_ciphertext) == raw_secret

    calls: list[str] = []

    def models_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["authorization"] == f"Bearer {raw_secret}"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "deepseek-v4"},
                    {"id": "qwen-planner"},
                    {"id": "gemma-review"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(models_handler)) as client:
        probe = ProviderProbeService(
            ProviderAdapterFactory(decrypt, http_client=client),
            repo,
        )
        # P0.2.1: Test Connection is connectivity-only (one /models handshake).
        connection = await probe.test_connection("ep-openrouter-test")
        assert connection.reachable is True
        assert connection.auth_valid is True
        assert connection.discovered_models == []
        assert calls == ["/v1/models"]

        # P0.2.1: Sync Models is the explicit discovery operation.
        sync = await probe.sync_models("ep-openrouter-test")

    assert sync.ok is True
    assert sorted(sync.added) == ["deepseek-v4", "gemma-review", "qwen-planner"]
    assert calls == ["/v1/models", "/v1/models"]
    assert session.query(EndpointModelBindingORM).count() == 3
    assert session.query(EndpointHealthSampleORM).one().healthy is True

    discovered = management.list_discovered_models("openrouter-test")
    canonical_by_name = {model["name"]: model["id"] for model in discovered}
    assignments = {
        "coding": canonical_by_name["deepseek-v4"],
        "planning": canonical_by_name["qwen-planner"],
        "review": canonical_by_name["gemma-review"],
    }
    for priority, (role, canonical_id) in enumerate(assignments.items(), start=1):
        management.upsert_model_rule(
            role=role,
            name=f"{role.title()} rule",
            primary_canonical_model_id=canonical_id,
            priority=priority,
            actor="phase10-test",
        )

    worker_bundle = ProviderComposer.compose(
        f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    loaded = {
        rule.task_labels[0]: rule.canonical_model_id
        for rule in worker_bundle.route_lock_service.current_ruleset.sorted_rules()
    }
    assert loaded == assignments

    settings = WorkerRuntimeSettings(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        fake_runtime=False,
        studio_runtime=True,
        studio_model_route=True,
        studio_canonical_model="",
        blender_engine=False,
        asset_gateway=False,
        asset_normalizer=False,
        artifact_root="artifacts",
        asset_library_root="data/assets/library",
        blender_executable="",
        certification_enabled=False,
        certification_conflict=False,
    )
    studio_route = StudioComposer.compose_provider_route(
        settings,
        worker_bundle.sync_factory,
        worker_bundle.lock_repo,
        worker_bundle.audit_repo,
        worker_bundle.binding_repo,
        worker_bundle.provider_management_repo,
    )
    receipt = await studio_route.studio_model_port.lock_route(
        SimpleNamespace(
            capability="coding",
            metadata={},
            prompt_spec=None,
            system="review system",
            user="review request",
        )
    )
    assert receipt.canonical_model_id == assignments["coding"]

    for role, canonical_id in assignments.items():
        lock = worker_bundle.route_lock_service.resolve_or_create_lock(
            RuleMatchContext(
                scope_type="studio_model",
                scope_id=f"phase10-{role}",
                task_labels=[role],
                available_capabilities=[role],
            )
        )
        assert lock.canonical_model_id == canonical_id

    session.expire_all()
    assert session.query(RouteLockV3ORM).count() == 4
    audit_rows = session.query(ProviderRoutingAuditV3ORM).all()
    audit_actions = {row.action for row in audit_rows}
    assert {"provider.add", "provider.probe", "provider.discovery", "rule.assign", "select"} <= audit_actions
    persisted_audit = "\n".join(row.metadata_json for row in audit_rows)
    assert raw_secret not in persisted_audit


@pytest.mark.asyncio
async def test_failed_real_probe_stays_failed_and_creates_no_binding(provider_db):
    _, factory = provider_db
    session = factory()
    repo = SQLProviderManagementRepository(session)
    management = ProviderManagementService(repo)
    management.add_provider(
        vendor_id="failed-provider",
        name="Failed Provider",
        base_url="https://failure.test/v1",
        protocol_mode="openai",
        credential_secret="synthetic-invalid-key",
        endpoint_id="ep-failed-provider",
    )

    def unauthorized(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(unauthorized)) as client:
        result = await ProviderProbeService(
            ProviderAdapterFactory(decrypt, http_client=client),
            repo,
        ).test_connection("ep-failed-provider")

    assert isinstance(result, ProviderProbeResult)
    assert result.reachable is False
    assert result.auth_valid is False
    assert session.query(EndpointModelBindingORM).count() == 0
    endpoint = session.query(ProviderEndpointORM).one()
    assert endpoint.test_status == "fail"
    assert management.get_provider("failed-provider")["status"] == "offline"


def test_http_add_connect_discover_and_assign_rule_gate(provider_db):
    _, factory = provider_db
    session = factory()
    repo = SQLProviderManagementRepository(session)
    management = ProviderManagementService(repo)
    raw_secret = "synthetic-http-gate-secret"

    def models_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {raw_secret}"
        return httpx.Response(200, json={"data": [{"id": "http-coder"}]})

    transport_client = httpx.AsyncClient(
        transport=httpx.MockTransport(models_handler)
    )
    probe = ProviderProbeService(
        ProviderAdapterFactory(decrypt, http_client=transport_client),
        repo,
    )

    class EmptyCatalog:
        async def list(self, _namespace):
            return []

        async def get(self, _namespace, _resource_id):
            return None

    app = FastAPI()
    app.include_router(providers_router)
    app.dependency_overrides[get_provider_management_service] = lambda: management
    app.dependency_overrides[get_provider_probe_service] = lambda: probe
    app.dependency_overrides[get_v3_resource_service] = EmptyCatalog

    with TestClient(app) as client:
        created = client.post(
            "/api/v3/providers",
            json={
                "id": "http-provider",
                "name": "HTTP Provider",
                "type": "cloud",
                "base_url": "https://http.test/v1",
                "protocol_mode": "openai",
                "api_key": raw_secret,
                "endpoint_id": "ep-http-provider",
            },
        )
        assert created.status_code == 201
        assert raw_secret not in created.text

        connected = client.post(
            "/api/v3/providers/http-provider/test-connection",
            json={"endpoint_id": "ep-http-provider"},
        )
        assert connected.status_code == 200
        assert connected.json()["reachable"] is True

        # P0.2.1: catalog refresh is the explicit Sync Models operation.
        import asyncio

        sync_receipt = asyncio.run(probe.sync_models("ep-http-provider"))
        assert sync_receipt.ok is True
        assert sync_receipt.added == ["http-coder"]

        models = client.get("/api/v3/providers/http-provider/models")
        assert models.status_code == 200
        canonical_id = models.json()[0]["id"]
        assigned = client.post(
            "/api/v3/providers/rules",
            json={
                "role": "coding",
                "name": "HTTP coding rule",
                "primary_canonical_model_id": canonical_id,
                "priority": 1,
            },
        )
        assert assigned.status_code == 201
        assert assigned.json()["primary_canonical_model_id"] == canonical_id

    credential = session.query(ProviderCredentialORM).one()
    assert credential.secret_ciphertext.startswith("enc:v1:")
    assert raw_secret not in credential.secret_ciphertext
    assert raw_secret not in "\n".join(
        row.metadata_json for row in session.query(ProviderRoutingAuditV3ORM).all()
    )


def test_add_provider_rolls_back_every_row_when_encryption_fails(
    provider_db, monkeypatch
):
    _, factory = provider_db
    session = factory()
    management = ProviderManagementService(SQLProviderManagementRepository(session))
    monkeypatch.delenv("WINDAGENT_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("WINDA_AGENT_ENCRYPTION_KEY", raising=False)

    with pytest.raises(EncryptionKeyMissingError):
        management.add_provider(
            vendor_id="atomic-provider",
            name="Atomic Provider",
            base_url="https://atomic.test/v1",
            credential_secret="must-not-persist",
            endpoint_id="ep-atomic-provider",
        )

    assert session.query(ProviderVendorORM).count() == 0
    assert session.query(ProviderCredentialORM).count() == 0
    assert session.query(ProviderEndpointORM).count() == 0
