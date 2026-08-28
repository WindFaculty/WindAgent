"""P0.1 — Provider lifecycle integration tests (edit / enable-disable /
delete-with-dependency-check / credential rotate-remove).

Follows the Phase 10 fixture pattern: dedicated SQLite tables, real AES-GCM
encryption key, real adapter code path against httpx.MockTransport, and the
real FastAPI providers router.
"""

from __future__ import annotations

import base64
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from windagent_providers.management import (
    ProviderAdapterFactory,
    ProviderInUseError,
    ProviderManagementService,
    ProviderVendorNotFoundError,
)
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointHealthSampleORM,
    EndpointModelBindingORM,
    EndpointRateLimitWindowORM,
    EndpointRuntimeStateORM,
    ModelDiscoverySnapshotORM,
    ModelRoutingRuleV3ORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    ProviderRoutingAuditV3ORM,
    ProviderVendorORM,
    RouteAttemptV3ORM,
    RouteLockV3ORM,
)
from windagent_storage.repositories.provider_management_repository import (
    SQLProviderManagementRepository,
)
from windagent_storage.security.encryption import decrypt
from windagent_api.dependencies import (
    get_provider_management_service,
    get_provider_probe_service,
    get_v3_resource_service,
)
from windagent_api.routers.v3.providers import router as providers_router


P01_TABLES = [
    ProviderVendorORM.__table__,
    ProviderCredentialORM.__table__,
    ProviderEndpointORM.__table__,
    CanonicalModelV3ORM.__table__,
    EndpointModelBindingORM.__table__,
    ModelRoutingRuleV3ORM.__table__,
    RouteLockV3ORM.__table__,
    ProviderRoutingAuditV3ORM.__table__,
    RouteAttemptV3ORM.__table__,
    EndpointRuntimeStateORM.__table__,
    EndpointHealthSampleORM.__table__,
    EndpointRateLimitWindowORM.__table__,
    ModelDiscoverySnapshotORM.__table__,
]


@pytest.fixture
def provider_db(tmp_path, monkeypatch):
    secret_key = base64.b64encode(b"k" * 32).decode()
    monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", secret_key)
    db_path = tmp_path / "p0_1.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    BaseORM.metadata.create_all(engine, tables=P01_TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield db_path, factory
    engine.dispose()


@pytest.fixture
def management(provider_db):
    _, factory = provider_db
    return ProviderManagementService(SQLProviderManagementRepository(factory()))


class EmptyCatalog:
    async def list(self, _namespace):
        return []

    async def get(self, _namespace, _resource_id):
        return None


@pytest.fixture
def api_client(provider_db, management):
    app = FastAPI()
    app.include_router(providers_router)
    app.dependency_overrides[get_provider_management_service] = lambda: management
    app.dependency_overrides[get_provider_probe_service] = lambda: object()
    app.dependency_overrides[get_v3_resource_service] = EmptyCatalog
    with TestClient(app) as client:
        yield client


def _seed_binding(session, vendor_id: str, endpoint_id: str, canonical_id: str) -> None:
    """Simulate a prior discovery snapshot: one canonical model + one binding."""
    session.add(
        CanonicalModelV3ORM(
            id=canonical_id,
            vendor="openai",
            family="gpt",
            canonical_name="Seeded Model",
            context_window=128000,
        )
    )
    session.add(
        EndpointModelBindingORM(
            id=f"bind-{uuid.uuid4().hex[:10]}",
            endpoint_id=endpoint_id,
            canonical_model_id=canonical_id,
            provider_model_id="seeded-model",
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# Edit / enable-disable
# ---------------------------------------------------------------------------


def test_update_provider_edits_name_base_url_and_enabled(management, provider_db):
    _, factory = provider_db
    management.add_provider(
        vendor_id="edit-provider",
        name="Original Name",
        base_url="https://old.test/v1",
        protocol_mode="openai",
        credential_secret="secret-edit-0000000001",
        endpoint_id="ep-edit-provider",
    )

    updated = management.update_provider(
        "edit-provider",
        name="Renamed Provider",
        base_url="https://new.test/v1",
        protocol_mode="ollama",
        actor="p01-test",
    )
    assert updated["display_name"] == "Renamed Provider"
    assert updated["endpoints"][0]["base_url"] == "https://new.test/v1"
    assert updated["endpoints"][0]["status"] == "unconfigured"

    disabled = management.update_provider("edit-provider", enabled=False)
    assert disabled["enabled"] is False
    assert disabled["status"] == "offline"

    re_enabled = management.update_provider("edit-provider", enabled=True)
    assert re_enabled["enabled"] is True
    assert re_enabled["status"] == "unconfigured"


def test_update_unknown_vendor_raises_vendor_not_found(management):
    with pytest.raises(ProviderVendorNotFoundError):
        management.update_provider("does-not-exist", name="Nope")


def test_rotate_credential_reencrypts_bumps_version_and_attaches_endpoints(
    management, provider_db
):
    _, factory = provider_db
    session = factory()
    management.add_provider(
        vendor_id="rotate-provider",
        name="Rotate Provider",
        base_url="https://rotate.test/v1",
        protocol_mode="openai",
        endpoint_id="ep-rotate-provider",
    )

    result = management.rotate_credential(
        "rotate-provider", "first-secret-000000000001", label="primary"
    )
    assert result["configured"] is True
    assert result["secret_version"] == 1

    rotated = management.rotate_credential(
        "rotate-provider", "rotated-secret-0000000002", label="primary-v2"
    )
    assert rotated["configured"] is True
    assert rotated["secret_version"] == 2
    assert "first-secret" not in str(rotated) and "rotated-secret" not in str(rotated)

    cred = session.query(ProviderCredentialORM).one()
    assert cred.secret_ciphertext.startswith("enc:v1:")
    assert decrypt(cred.secret_ciphertext) == "rotated-secret-0000000002"
    assert cred.secret_version == 2
    assert cred.label == "primary-v2"

    endpoint = session.query(ProviderEndpointORM).filter_by(id="ep-rotate-provider").one()
    assert endpoint.credential_id == cred.id
    assert management.get_provider("rotate-provider")["has_credentials"] is True


async def test_probe_uses_rotated_secret(management, provider_db):
    _, factory = provider_db
    session = factory()
    repo = SQLProviderManagementRepository(session)
    management.add_provider(
        vendor_id="probe-rotate",
        name="Probe Rotate",
        base_url="https://probe.test/v1",
        protocol_mode="openai",
        credential_secret="old-key-aaaaaaaaaaaa",
        endpoint_id="ep-probe-rotate",
    )
    management.rotate_credential("probe-rotate", "new-key-bbbbbbbbbbbbbb")

    seen_headers: list[str] = []

    def models_handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers["authorization"])
        return httpx.Response(200, json={"data": [{"id": "probe-model"}]})

    from windagent_providers.management import ProviderProbeService

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(models_handler)
    ) as client:
        result = await ProviderProbeService(
            ProviderAdapterFactory(decrypt, http_client=client), repo
        ).test_connection("ep-probe-rotate")

    assert result.reachable is True
    # health() performs exactly one /models handshake (P0.2.1 split).
    assert seen_headers == ["Bearer new-key-bbbbbbbbbbbbbb"]


def test_remove_credential_detaches_endpoints_and_clears_probe_material(
    management, provider_db
):
    _, factory = provider_db
    session = factory()
    management.add_provider(
        vendor_id="cred-remove",
        name="Cred Remove",
        base_url="https://remove.test/v1",
        protocol_mode="openai",
        credential_secret="doomed-secret-0000000003",
        endpoint_id="ep-cred-remove",
    )

    result = management.remove_credential("cred-remove")
    assert result["configured"] is False

    assert session.query(ProviderCredentialORM).count() == 0
    endpoint = session.query(ProviderEndpointORM).filter_by(id="ep-cred-remove").one()
    assert endpoint.credential_id is None

    public = management.get_provider("cred-remove")
    assert public["has_credentials"] is False

    repo = SQLProviderManagementRepository(session)
    material = repo.get_probe_material("ep-cred-remove")
    assert material is not None
    assert material.credential_ciphertext is None


# ---------------------------------------------------------------------------
# Delete with routing-rule dependency check
# ---------------------------------------------------------------------------


def _add_provider_with_bound_model(management, session, vendor_id: str) -> str:
    management.add_provider(
        vendor_id=vendor_id,
        name=f"{vendor_id.title()} Provider",
        base_url=f"https://{vendor_id}.test/v1",
        protocol_mode="openai",
        credential_secret=f"{vendor_id}-secret-000000004",
        endpoint_id=f"ep-{vendor_id}",
    )
    canonical_id = f"canon-{vendor_id}"
    _seed_binding(session, vendor_id, f"ep-{vendor_id}", canonical_id)
    return canonical_id


def test_delete_blocked_while_routing_rule_references_bound_model(
    management, provider_db
):
    _, factory = provider_db
    session = factory()
    canonical_id = _add_provider_with_bound_model(management, session, "blocked-del")
    management.upsert_model_rule(
        role="studio.story.screenplay.generate",
        name="Screenplay writer",
        primary_canonical_model_id=canonical_id,
    )

    with pytest.raises(ProviderInUseError) as excinfo:
        management.delete_provider("blocked-del")
    assert excinfo.value.blocking_rules[0]["role"] == "studio.story.screenplay.generate"

    # Provider untouched after the failed delete.
    assert management.get_provider("blocked-del") is not None
    assert session.query(ModelRoutingRuleV3ORM).count() == 1


def test_delete_blocked_by_fallback_reference_too(management, provider_db):
    _, factory = provider_db
    session = factory()
    canonical_id = _add_provider_with_bound_model(management, session, "fallback-del")
    other = management.add_provider(
        vendor_id="other-del",
        name="Other",
        base_url="https://other.test/v1",
        protocol_mode="openai",
        endpoint_id="ep-other-del",
    )
    assert other is not None
    management.rotate_credential("other-del", "other-secret-0000000005")
    _seed_binding(session, "other-del", "ep-other-del", "canon-other-del")

    management.upsert_model_rule(
        role="coding",
        name="Coding rule",
        primary_canonical_model_id="canon-other-del",
        fallback_canonical_model_id=canonical_id,
    )

    with pytest.raises(ProviderInUseError):
        management.delete_provider("fallback-del")


def test_delete_with_explicit_opt_in_disables_rules_then_removes_rows(
    management, provider_db
):
    _, factory = provider_db
    session = factory()
    canonical_id = _add_provider_with_bound_model(management, session, "cascade-del")
    management.upsert_model_rule(
        role="planning",
        name="Planning rule",
        primary_canonical_model_id=canonical_id,
    )

    result = management.delete_provider(
        "cascade-del", allow_disabling_rules=True, actor="p01-test"
    )
    assert result["deleted"] is True
    assert result["removed_endpoints"] == 1
    assert result["removed_bindings"] == 1
    assert result["disabled_rule_roles"] == ["planning"]

    assert management.get_provider("cascade-del") is None
    assert session.query(ProviderVendorORM).count() == 0
    assert session.query(ProviderEndpointORM).count() == 0
    assert session.query(ProviderCredentialORM).count() == 0
    assert session.query(EndpointModelBindingORM).count() == 0
    # Canonical identity survives (shared catalog, not provider-owned).
    assert session.query(CanonicalModelV3ORM).count() == 1
    # The conflicting rule is disabled, not silently deleted.
    assert session.query(ModelRoutingRuleV3ORM).filter_by(role="planning").one().enabled is False
    assert management.list_enabled_model_rules() == []

    audit_actions = {row.action for row in session.query(ProviderRoutingAuditV3ORM).all()}
    assert {"provider.delete", "rule.disable"} <= audit_actions
    # Removed-row accounting persisted in the audit metadata.
    delete_rows = [
        row
        for row in session.query(ProviderRoutingAuditV3ORM).all()
        if row.action == "provider.delete"
    ]
    assert len(delete_rows) == 1


def test_delete_clean_provider_removes_dependent_execution_rows(
    management, provider_db
):
    _, factory = provider_db
    session = factory()
    management.add_provider(
        vendor_id="clean-del",
        name="Clean Del",
        base_url="https://clean.test/v1",
        protocol_mode="openai",
        credential_secret="clean-secret-00000000006",
        endpoint_id="ep-clean-del",
    )
    _seed_binding(session, "clean-del", "ep-clean-del", "canon-clean-del")
    # Simulate execution leftovers that hold FKs into endpoints/bindings.
    session.add(
        EndpointRuntimeStateORM(endpoint_id="ep-clean-del", consecutive_failures=2)
    )
    session.add(
        EndpointHealthSampleORM(
            endpoint_id="ep-clean-del", healthy=False, latency_ms=12.5
        )
    )
    session.add(
        ModelDiscoverySnapshotORM(
            id=f"snap-{uuid.uuid4().hex[:8]}",
            endpoint_id="ep-clean-del",
            raw_response_json="{}",
        )
    )
    session.commit()

    result = management.delete_provider("clean-del")
    assert result["deleted"] is True
    assert result["removed_bindings"] == 1

    assert session.query(ProviderVendorORM).count() == 0
    assert session.query(EndpointModelBindingORM).count() == 0
    assert session.query(EndpointHealthSampleORM).count() == 0
    assert session.query(ModelDiscoverySnapshotORM).count() == 0
    assert session.query(EndpointRuntimeStateORM).count() == 0


def test_delete_unknown_vendor_raises(management):
    with pytest.raises(ProviderVendorNotFoundError):
        management.delete_provider("ghost")


# ---------------------------------------------------------------------------
# HTTP contract level
# ---------------------------------------------------------------------------


def test_http_lifecycle_patch_delete_and_credential_routes(api_client, provider_db):
    _, factory = provider_db
    session = factory()
    created = api_client.post(
        "/api/v3/providers",
        json={
            "id": "http-life",
            "name": "HTTP Life",
            "type": "cloud",
            "base_url": "https://life.test/v1",
            "protocol_mode": "openai",
            "api_key": "http-secret-000000000007",
            "endpoint_id": "ep-http-life",
        },
    )
    assert created.status_code == 201

    patched = api_client.patch(
        "/api/v3/providers/http-life",
        json={"name": "HTTP Life v2", "base_url": "https://life2.test/v1"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["display_name"] == "HTTP Life v2"
    assert body["endpoints"][0]["base_url"] == "https://life2.test/v1"

    disabled = api_client.patch(
        "/api/v3/providers/http-life", json={"enabled": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["status"] == "offline"

    rotated = api_client.put(
        "/api/v3/providers/http-life/credential",
        json={"api_key": "rotated-http-00000000008", "label": "rotated"},
    )
    assert rotated.status_code == 200
    rotation_body = rotated.json()
    assert rotation_body["configured"] is True
    assert rotation_body["secret_version"] == 2
    assert "rotated-http" not in patched.text and "rotated-http" not in rotated.text

    removed = api_client.delete("/api/v3/providers/http-life/credential")
    assert removed.status_code == 200
    assert removed.json()["configured"] is False
    assert session.query(ProviderCredentialORM).count() == 0

    _seed_binding(session, "http-life", "ep-http-life", "canon-http-life")
    api_client.put(
        "/api/v3/providers/http-life/credential",
        json={"api_key": "final-http-000000000009"},
    )
    management = ProviderManagementService(SQLProviderManagementRepository(session))
    management.upsert_model_rule(
        role="review",
        name="Review rule",
        primary_canonical_model_id="canon-http-life",
    )

    conflict = api_client.delete("/api/v3/providers/http-life")
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["blocking_rules"][0]["role"] == "review"

    allowed = api_client.delete(
        "/api/v3/providers/http-life",
        params={"allow_disabling_rules": "true"},
    )
    assert allowed.status_code == 200
    delete_body = allowed.json()
    assert delete_body["deleted"] is True
    assert delete_body["disabled_rule_roles"] == ["review"]

    gone = api_client.get("/api/v3/providers/http-life")
    assert gone.status_code == 404


def test_create_provider_reports_unavailable_credential_storage(api_client, monkeypatch):
    """A missing encryption key must not surface as an opaque 500 response."""
    monkeypatch.delenv("WINDAGENT_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("WINDA_AGENT_ENCRYPTION_KEY", raising=False)

    response = api_client.post(
        "/api/v3/providers",
        json={
            "id": "openrouter",
            "name": "OpenRouter",
            "type": "cloud",
            "base_url": "https://openrouter.ai/api/v1",
            "protocol_mode": "openai",
            "api_key": "test-key-not-a-real-secret",
        },
    )

    assert response.status_code == 503
    assert "WINDAGENT_ENCRYPTION_KEY" in response.json()["detail"]


def test_http_mutations_fail_closed_for_catalog_only_providers(api_client):
    patch = api_client.patch(
        "/api/v3/providers/catalog-only", json={"name": "nope"}
    )
    assert patch.status_code == 404

    delete = api_client.delete("/api/v3/providers/catalog-only")
    assert delete.status_code == 404

    put = api_client.put(
        "/api/v3/providers/catalog-only/credential", json={"api_key": "x"}
    )
    assert put.status_code == 404

    remove = api_client.delete("/api/v3/providers/catalog-only/credential")
    assert remove.status_code == 404


def test_raw_secrets_never_leak_into_responses_or_audit(api_client, provider_db):
    _, factory = provider_db
    session = factory()
    secrets = ["leak-one-000000000000010", "leak-two-00000000000011"]
    api_client.post(
        "/api/v3/providers",
        json={
            "id": "leak-check",
            "name": "Leak Check",
            "base_url": "https://leak.test/v1",
            "protocol_mode": "openai",
            "api_key": secrets[0],
            "endpoint_id": "ep-leak-check",
        },
    )
    api_client.put(
        "/api/v3/providers/leak-check/credential", json={"api_key": secrets[1]}
    )
    api_client.patch("/api/v3/providers/leak-check", json={"name": "Leak Renamed"})
    api_client.delete("/api/v3/providers/leak-check")

    audit_blob = "\n".join(
        row.metadata_json or "" for row in session.query(ProviderRoutingAuditV3ORM).all()
    )
    reasons = "\n".join(
        row.reason or "" for row in session.query(ProviderRoutingAuditV3ORM).all()
    )
    for secret in secrets:
        assert secret not in audit_blob
        assert secret not in reasons
