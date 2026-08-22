"""P0.2 — Model Discovery & Catalog integration tests.

Covers:
- P0.2.1  Sync Models is independent from Test Connection
- P0.2.2  durable registry metadata (pricing_class/prices/last_discovered_at)
- P0.2.3  FREE/PAID/UNKNOWN classification strictly from provider data
- P0.2.4  reconciliation ADDED/UPDATED/UNCHANGED/UNAVAILABLE (never deletes)
- P0.2.5  Test Model probe with one tiny REAL inference
"""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from windagent_providers.management import (
    ProviderAdapterFactory,
    ProviderManagementService,
    ProviderProbeService,
)
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
from windagent_api.routers.v3.models import router as models_router
from windagent_api.routers.v3.providers import router as providers_router


P02_TABLES = [
    ProviderVendorORM.__table__,
    ProviderCredentialORM.__table__,
    ProviderEndpointORM.__table__,
    CanonicalModelV3ORM.__table__,
    EndpointModelBindingORM.__table__,
    ModelRoutingRuleV3ORM.__table__,
    RouteLockV3ORM.__table__,
    ProviderRoutingAuditV3ORM.__table__,
    RouteAttemptV3ORM.__table__,
    EndpointHealthSampleORM.__table__,
]


@pytest.fixture
def catalog_db(tmp_path, monkeypatch):
    secret_key = base64.b64encode(b"c" * 32).decode()
    monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", secret_key)
    monkeypatch.delenv("WINDAGENT_PROFILE", raising=False)
    db_path = tmp_path / "p0_2.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    BaseORM.metadata.create_all(engine, tables=P02_TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield db_path, factory
    engine.dispose()


def _openrouter_payload(models: list[dict]) -> dict:
    return {"data": models}


PAID_ITEM = {
    "id": "anthropic/claude-sonnet",
    "name": "Claude Sonnet",
    "context_length": 200000,
    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
}
FREE_ITEM = {
    "id": "deepseek/deepseek-r1:free",
    "name": "DeepSeek R1 (free)",
    "context_length": 64000,
    "pricing": {"prompt": "0", "completion": "0"},
}
NO_PRICING_ITEM = {
    "id": "meta/llama-3-8b",
    "name": "Llama 3 8B",
    "context_length": 8192,
}


class CatalogHarness:
    """Wires provider + probe services against a scripted /models transport."""

    def __init__(self, factory, items: list[dict]):
        self.session = factory()
        self.repo = SQLProviderManagementRepository(self.session)
        self.management = ProviderManagementService(self.repo)
        self.calls: list[str] = []
        self._items = items
        raw_secret = "catalog-sync-secret-00000012"

        def handler(request: httpx.Request) -> httpx.Response:
            self.calls.append(request.url.path)
            return httpx.Response(200, json=_openrouter_payload(self._items))

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.probe = ProviderProbeService(
            ProviderAdapterFactory(decrypt, http_client=client), self.repo
        )
        self.raw_secret = raw_secret
        self.management.add_provider(
            vendor_id="openrouter",
            name="OpenRouter",
            vendor_type="cloud",
            base_url="https://openrouter.test/api/v1",
            protocol_mode="openai",
            credential_secret=raw_secret,
            endpoint_id="ep-openrouter",
            actor="p02-test",
        )

    def set_items(self, items: list[dict]) -> None:
        self._items = items


@pytest.fixture
def harness(catalog_db):
    _, factory = catalog_db
    return CatalogHarness(factory, [PAID_ITEM, FREE_ITEM, NO_PRICING_ITEM])


# ---------------------------------------------------------------------------
# P0.2.1 + P0.2.4 — sync/reconciliation semantics
# ---------------------------------------------------------------------------


async def test_sync_models_is_independent_from_test_connection(harness):
    # Test Connection performs exactly ONE network handshake, registers nothing.
    connection = await harness.probe.test_connection("ep-openrouter")
    assert connection.reachable is True
    assert connection.auth_valid is True
    assert connection.discovered_models == []
    assert harness.session.query(EndpointModelBindingORM).count() == 0

    # Sync Models is the explicit discovery operation.
    sync = await harness.probe.sync_models("ep-openrouter")
    assert sync.ok is True
    assert sorted(sync.discovered) == [
        "anthropic/claude-sonnet",
        "deepseek/deepseek-r1:free",
        "meta/llama-3-8b",
    ]
    assert len(sync.added) == 3 and sync.unavailable == []


async def test_reconciliation_classifies_added_unchanged_unavailable_updated(harness):
    first = await harness.probe.sync_models("ep-openrouter")
    assert len(first.added) == 3 and not first.updated and not first.unavailable

    # Same catalog again → everything UNCHANGED.
    second = await harness.probe.sync_models("ep-openrouter")
    assert second.added == [] and second.updated == []
    assert sorted(second.unchanged) == sorted(first.discovered)

    # One model disappears from the provider → UNAVAILABLE, never deleted.
    harness.set_items([PAID_ITEM, FREE_ITEM])
    third = await harness.probe.sync_models("ep-openrouter")
    assert third.unavailable == ["meta/llama-3-8b"]
    assert harness.session.query(EndpointModelBindingORM).count() == 3

    # It reappears (with a new price) → back to ACTIVE, counted as UPDATED.
    harness.set_items(
        [
            PAID_ITEM,
            FREE_ITEM,
            {**NO_PRICING_ITEM, "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        ]
    )
    fourth = await harness.probe.sync_models("ep-openrouter")
    assert fourth.unavailable == []
    assert fourth.updated == ["meta/llama-3-8b"]
    assert sorted(fourth.unchanged) == [
        "anthropic/claude-sonnet",
        "deepseek/deepseek-r1:free",
    ]

    rows = {
        row.provider_model_id: row
        for row in harness.session.query(EndpointModelBindingORM).all()
    }
    assert rows["meta/llama-3-8b"].availability == "active"
    assert rows["meta/llama-3-8b"].enabled is True
    assert rows["meta/llama-3-8b"].pricing_class == "PAID"


# ---------------------------------------------------------------------------
# P0.2.2/P0.2.3 — truthful pricing metadata
# ---------------------------------------------------------------------------


async def test_pricing_classified_only_from_provider_advertised_data(harness):
    await harness.probe.sync_models("ep-openrouter")
    rows = {
        row.provider_model_id: row
        for row in harness.session.query(EndpointModelBindingORM).all()
    }

    paid_row = rows["anthropic/claude-sonnet"]
    assert paid_row.pricing_class == "PAID"
    assert paid_row.input_price == pytest.approx(0.000003)
    assert paid_row.output_price == pytest.approx(0.000015)
    assert paid_row.currency == "USD"
    assert paid_row.last_discovered_at is not None

    free_row = rows["deepseek/deepseek-r1:free"]
    assert free_row.pricing_class == "FREE"
    assert free_row.input_price == 0.0 and free_row.output_price == 0.0

    unknown_row = rows["meta/llama-3-8b"]
    assert unknown_row.pricing_class == "UNKNOWN"
    assert unknown_row.input_price is None and unknown_row.output_price is None
    assert unknown_row.currency is None


async def test_provider_models_endpoint_filters_by_pricing_class(harness):
    await harness.probe.sync_models("ep-openrouter")

    class EmptyCatalog:
        async def list(self, _namespace):
            return []

        async def get(self, _namespace, _resource_id):
            return None

    app = FastAPI()
    app.include_router(providers_router)
    app.dependency_overrides[get_provider_management_service] = lambda: harness.management
    app.dependency_overrides[get_v3_resource_service] = EmptyCatalog
    with TestClient(app) as client:
        all_models = client.get("/api/v3/providers/openrouter/models")
        assert all_models.status_code == 200
        assert len(all_models.json()) == 3

        free = client.get("/api/v3/providers/openrouter/models", params={"pricing": "free"})
        free_provider_ids = {
            b["provider_model_id"] for m in free.json() for b in m["bindings"]
        }
        assert free_provider_ids == {"deepseek/deepseek-r1:free"}

        paid = client.get("/api/v3/providers/openrouter/models", params={"pricing": "PAID"})
        paid_ids = {
            b["provider_model_id"]
            for m in paid.json()
            for b in m["bindings"]
        }
        assert paid_ids == {"anthropic/claude-sonnet"}

        invalid = client.get("/api/v3/providers/openrouter/models", params={"pricing": "cheap"})
        assert invalid.status_code == 422


async def test_models_router_serves_durable_registry_with_pricing_filter(
    harness, catalog_db, monkeypatch
):
    await harness.probe.sync_models("ep-openrouter")

    class EmptyCatalog:
        async def list(self, _namespace):
            return []

        async def get(self, _namespace, _resource_id):
            return None

    app = FastAPI()
    app.include_router(models_router)
    app.include_router(providers_router)
    app.dependency_overrides[get_provider_management_service] = lambda: harness.management
    app.dependency_overrides[get_v3_resource_service] = EmptyCatalog

    with TestClient(app) as client:
        catalog = client.get("/api/v3/models")
        assert catalog.status_code == 200
        catalog_json = catalog.json()
        assert len(catalog_json) == 3

        def find(fragment: str) -> dict:
            return next(
                m for m in catalog_json
                if fragment in m["name"].lower() or fragment in m["id"].lower()
            )

        claude = find("claude")
        r1 = find("r1")
        llama = find("llama")
        assert claude["pricing_class"] == "PAID"
        assert r1["pricing_class"] == "FREE"
        assert llama["pricing_class"] == "UNKNOWN"
        binding = claude["bindings"][0]
        assert binding["pricing_class"] == "PAID"
        assert binding["provider_id"] == "openrouter"
        assert binding["endpoint_id"] == "ep-openrouter"
        assert binding["last_discovered_at"] is not None

        free_only = client.get("/api/v3/models", params={"pricing": "FREE"})
        free_ids = {m["id"] for m in free_only.json()}
        assert r1["id"] in free_ids
        assert claude["id"] not in free_ids

        unknown_only = client.get("/api/v3/models", params={"pricing": "UNKNOWN"})
        assert {m["id"] for m in unknown_only.json()} == {llama["id"]}

        detail = client.get(f"/api/v3/models/{claude['id']}")
        assert detail.status_code == 200
        assert detail.json()["pricing_class"] == "PAID"


# ---------------------------------------------------------------------------
# P0.2.5 — Test Model probe (tiny real inference)
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Minimal adapter standing in for the real OpenAI-compatible transport."""

    def __init__(self, material, responder=None, failer=None):
        self.material = material
        self._responder = responder
        self._failer = failer

    async def health(self):  # pragma: no cover - unused in these tests
        from windagent_core.contracts.providers.capabilities import ProviderHealth

        return ProviderHealth(provider_name=self.material.vendor_id, healthy=True)

    async def list_models(self):  # pragma: no cover - covered via probe service elsewhere
        return []

    async def generate(self, request, model_id):
        if self._failer is not None:
            raise self._failer
        from windagent_providers.base.contracts import (
            FinishReason,
            ProviderResponse,
            ProviderUsage,
        )

        assert request.max_output_tokens <= 16, "model probe must stay a tiny inference"
        return ProviderResponse(
            canonical_model_id=model_id,
            provider_model_id=model_id,
            endpoint_id=self.material.endpoint_id,
            text="OK",
            finish_reason=FinishReason.STOP.value,
            usage=ProviderUsage(prompt_tokens=9, completion_tokens=1),
            total_latency_ms=42.0,
        )


async def test_model_probe_success_and_fail_closed(harness, monkeypatch):
    await harness.probe.sync_models("ep-openrouter")

    canonical_paid = harness.management.list_discovered_models("openrouter")
    claude_entry = next(m for m in canonical_paid if "claude" in m["name"])
    canonical_id = claude_entry["id"]

    material = harness.repo.get_probe_material("ep-openrouter")
    ok_adapter = _StubAdapter(material)
    monkeypatch.setattr(harness.probe, "_adapter_factory", type("F", (), {"create": staticmethod(lambda m: ok_adapter)}))

    receipt = await harness.probe.probe_model("ep-openrouter", canonical_id)
    assert receipt.ok is True
    assert receipt.provider_model_id == "anthropic/claude-sonnet"
    assert receipt.finish_reason == "stop"
    assert receipt.error_code is None
    assert receipt.latency_ms >= 0

    from windagent_providers.base.errors import RateLimitFailure

    fail_adapter = _StubAdapter(
        None,
        failer=RateLimitFailure("429 slow down", provider_id="openrouter"),
    )
    monkeypatch.setattr(
        harness.probe,
        "_adapter_factory",
        type("F", (), {"create": staticmethod(lambda m: fail_adapter)}),
    )
    failed = await harness.probe.probe_model("ep-openrouter", canonical_id)
    assert failed.ok is False
    assert failed.error_code == "RateLimitFailure"

    audit_actions = {
        row.action for row in harness.session.query(ProviderRoutingAuditV3ORM).all()
    }
    assert "provider.model_probe" in audit_actions


async def test_model_probe_fails_closed_for_unbound_model(harness):
    receipt = await harness.probe.probe_model("ep-openrouter", "cm-does-not-exist")
    assert receipt.ok is False
    assert receipt.error_code == "MODEL_NOT_BOUND"


def test_sync_models_http_route_is_explicit_operation(catalog_db):
    """HTTP-level: sync-models works standalone right after registration."""
    _, factory = catalog_db
    harness = CatalogHarness(factory, [FREE_ITEM])

    app = FastAPI()
    app.include_router(providers_router)
    app.dependency_overrides[get_provider_management_service] = lambda: harness.management
    app.dependency_overrides[get_provider_probe_service] = lambda: harness.probe

    class EmptyCatalog:
        async def list(self, _namespace):
            return []

        async def get(self, _namespace, _resource_id):
            return None

    app.dependency_overrides[get_v3_resource_service] = EmptyCatalog

    with TestClient(app) as client:
        synced = client.post("/api/v3/providers/openrouter/sync-models", json={})
        assert synced.status_code == 200
        body = synced.json()
        assert body["ok"] is True
        assert body["added"] == ["deepseek/deepseek-r1:free"]
        assert body["discovered_count"] == 1

        again = client.post("/api/v3/providers/openrouter/sync-models", json={})
        assert again.json()["unchanged"] == ["deepseek/deepseek-r1:free"]

    credential = harness.session.query(ProviderCredentialORM).one()
    assert decrypt(credential.secret_ciphertext) == harness.raw_secret
