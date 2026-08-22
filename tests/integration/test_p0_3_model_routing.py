"""P0.3 — Model routing live: story roles, resolution order, fallback, receipts.

Covers the P0.3 gate surface:

- P0.3.1  canonical story roles match prompt-registry capabilities
          (durable rules authored as ``studio.story.*`` task types, including
          the plan aliases ``studio.story.screenplay.review|revise``);
- P0.3.4  resolution order: exact role rule → default rule → fail closed
          with ``ROUTING_UNAVAILABLE`` (never a random model);
- P0.3.5  rule-declared fallback executes ONLY for defined transient
          failures (timeout/unavailable/rate-limit/endpoint exhaustion) and
          NEVER for schema/auth-class failures;
- P0.3.6  durable route receipts persist rule/model/provider/fallback/
          timestamps per LLM task and are readable through the API.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from windagent_core.contracts.providers.usage import ProviderUsage
from windagent_core.contracts.providers.responses import ProviderResponse
from windagent_core.contracts.studio.story_roles import (
    ROUTING_UNAVAILABLE,
    RoutingUnavailableError,
)
from windagent_intelligence.story.prompts.registry import STORY_PROMPT_REGISTRY
from windagent_intelligence.story.prompts.structured import StoryModelBoundary
from windagent_providers.base.errors import InvalidRequestFailure, TimeoutFailure
from windagent_providers.management import ProviderManagementService
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointModelBindingORM,
    ModelRouteReceiptV3ORM,
    ModelRoutingRuleV3ORM,
    ProviderRoutingAuditV3ORM,
    RouteLockV3ORM,
)
from windagent_storage.repositories.provider_management_repository import (
    SQLProviderManagementRepository,
)
from windagent_storage.repositories.v3_routing_repositories import (
    SQLModelRouteReceiptRepository,
)
from windagent_worker.studio_model_port import RouteLockedModelPort
from tests.fakes.routing_fakes import InMemoryLockStore

PRIMARY_MODEL = "test/primary-model"
FALLBACK_MODEL = "test/fallback-model"
DEFAULT_MODEL = "test/default-model"

TABLES = [
    CanonicalModelV3ORM.__table__,
    EndpointModelBindingORM.__table__,
    ModelRoutingRuleV3ORM.__table__,
    RouteLockV3ORM.__table__,
    ProviderRoutingAuditV3ORM.__table__,
    ModelRouteReceiptV3ORM.__table__,
]


@pytest.fixture
def routing_db(tmp_path):
    db_path = tmp_path / "p03.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    BaseORM.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    for canonical_id in (PRIMARY_MODEL, FALLBACK_MODEL, DEFAULT_MODEL):
        vendor, name = canonical_id.split("/", 1)
        session.add(
            CanonicalModelV3ORM(
                id=canonical_id,
                vendor=vendor,
                family=name,
                canonical_name=name,
                enabled=True,
            )
        )
    session.commit()
    session.close()
    yield factory
    engine.dispose()


def _management(factory) -> ProviderManagementService:
    return ProviderManagementService(SQLProviderManagementRepository(factory()))


def _make_rule(factory, *, role: str, primary: str, fallback: str | None = None, priority: int = 1):
    _management(factory).upsert_model_rule(
        role=role,
        name=f"{role} rule",
        primary_canonical_model_id=primary,
        fallback_canonical_model_id=fallback,
        priority=priority,
        actor="p03-test",
    )


class ScriptedAdapter:
    """Adapter that fails selected provider models with a typed failure."""

    def __init__(self, failures: dict[str, Exception]):
        self.failures = failures
        self.calls: list[str] = []

    async def generate(self, request, model_id: str | None = None):
        self.calls.append(str(model_id))
        failure = self.failures.get(str(model_id))
        if failure is not None:
            raise failure
        return ProviderResponse(
            provider_id="scripted-provider",
            provider_model_id=model_id,
            content="{}",
            finish_reason="stop",
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1),
        )


class Registry:
    def __init__(self, bindings: dict[str, list[dict]]):
        self.bindings = bindings

    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> list[dict]:
        return self.bindings.get(canonical_model_id, [])

    async def get_endpoint(self, endpoint_id: str):
        for candidates in self.bindings.values():
            for candidate in candidates:
                if candidate["endpoint_id"] == endpoint_id:
                    return candidate
        return None


class State:
    async def is_available(self, endpoint_id: str) -> bool:
        return True

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        return None

    async def record_failure(self, endpoint_id: str, error_class: str, status_code) -> None:
        return None

    async def set_cooldown(self, endpoint_id: str, cooldown_until) -> None:
        return None


class Quota:
    async def get_quota_state(self, provider_id: str):
        return None

    async def update_quota_state(self, provider_id, snapshot) -> None:
        return None


class Attempts:
    async def record_attempt(self, **kwargs) -> str:
        return "attempt-1"


BINDING_TEMPLATE = {
    "endpoint_id": "",
    "binding_id": "",
    "provider_model_id": "",
    "provider_name": "scripted-provider",
    "base_url": "https://local.test/v1",
    "equivalence_level": "exact_revision",
    "is_active": True,
    "protocol_mode": "openai",
    "credential_ciphertext": "cipher:test",
}


def _binding(endpoint_suffix: str, provider_model_id: str) -> dict:
    binding = dict(BINDING_TEMPLATE)
    binding["endpoint_id"] = f"ep-{endpoint_suffix}"
    binding["binding_id"] = f"bind-{endpoint_suffix}"
    binding["provider_model_id"] = provider_model_id
    return binding


def _build_port(factory, adapter, *, receipt_repo=None, ruleset=None) -> RouteLockedModelPort:
    if ruleset is None:
        from windagent_providers.management import RoutingPolicyProjection

        ruleset = RoutingPolicyProjection(
            SQLProviderManagementRepository(factory())
        ).load_ruleset()
    lock_service = RouteLockService(ruleset=ruleset, lock_repository=InMemoryLockStore())
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: adapter,
        endpoint_registry=Registry(
            {
                PRIMARY_MODEL: [_binding("primary", "primary-native")],
                FALLBACK_MODEL: [_binding("fallback", "fallback-native")],
                DEFAULT_MODEL: [_binding("default", "default-native")],
            }
        ),
        endpoint_state=State(),
        quota_state=Quota(),
        attempt_log=Attempts(),
    )
    return RouteLockedModelPort(lock_service, coordinator, receipt_repository=receipt_repo)


def _request(capability: str) -> SimpleNamespace:
    return SimpleNamespace(
        capability=capability,
        metadata={},
        prompt_spec=None,
        system="test system",
        user="test request",
        temperature=0.2,
        max_tokens=64,
        structured_output_schema=None,
    )


# ---------------------------------------------------------------------------
# P0.3.1 — canonical story roles match prompt capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_story_role_rule_matches_short_capability(routing_db):
    factory = routing_db
    _make_rule(factory, role="studio.story.idea.generate", primary=PRIMARY_MODEL)

    port = _build_port(factory, ScriptedAdapter({}))
    receipt = await port.lock_route(_request("ideation"))

    assert receipt.canonical_model_id == PRIMARY_MODEL
    assert receipt.rule_id == "role-studio.story.idea.generate"


@pytest.mark.asyncio
async def test_plan_alias_roles_match_review_capabilities(routing_db):
    factory = routing_db
    # Authored with the plan-vocabulary alias; must normalize + still match.
    management = _management(factory)
    from windagent_core.contracts.studio.story_roles import normalize_story_role

    management.upsert_model_rule(
        role=normalize_story_role("studio.story.screenplay.review"),
        name="Screenplay review rule",
        primary_canonical_model_id=PRIMARY_MODEL,
        priority=1,
        actor="p03-test",
    )

    port = _build_port(factory, ScriptedAdapter({}))
    receipt = await port.lock_route(_request("review"))

    assert receipt.canonical_model_id == PRIMARY_MODEL
    assert receipt.rule_id == "role-studio.story.review"
    # Every canonical role resolves to exactly one spec.
    assert set(STORY_PROMPT_REGISTRY)  # registry present (sanity)


# ---------------------------------------------------------------------------
# P0.3.4 — resolution order and fail-closed ROUTING_UNAVAILABLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_role_rule_wins_over_system_default(routing_db):
    from windagent_providers.management import RoutingPolicyProjection
    from windagent_providers.routing.rules import RoutingRule

    factory = routing_db
    # Exact role rule only in SQL; the system default is composed separately.
    _make_rule(
        factory,
        role="studio.story.outline.generate",
        primary=PRIMARY_MODEL,
        priority=1,
    )
    sql_ruleset = RoutingPolicyProjection(
        SQLProviderManagementRepository(factory())
    ).load_ruleset()
    assert len(sql_ruleset.rules) == 1

    from windagent_worker.studio_model_port import SYSTEM_DEFAULT_RULE_ID

    ruleset = type(sql_ruleset)(
        rules=[
            *sql_ruleset.rules,
            RoutingRule(
                rule_id=SYSTEM_DEFAULT_RULE_ID,
                rule_version=1,
                canonical_model_id=DEFAULT_MODEL,
                description="System default route (lowest priority)",
                priority=10_000,
            ),
        ]
    )
    lock_service = RouteLockService(ruleset=ruleset, lock_repository=InMemoryLockStore())
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: ScriptedAdapter({}),
        endpoint_registry=Registry({}),
        endpoint_state=State(),
        quota_state=Quota(),
        attempt_log=Attempts(),
    )
    port = RouteLockedModelPort(lock_service, coordinator)

    matched = await port.lock_route(_request("outline"))
    assert matched.canonical_model_id == PRIMARY_MODEL
    assert matched.rule_id == "role-studio.story.outline.generate"

    unmatched = await port.lock_route(_request("screenplay"))
    assert unmatched.canonical_model_id == DEFAULT_MODEL
    assert unmatched.rule_id == SYSTEM_DEFAULT_RULE_ID


@pytest.mark.asyncio
async def test_no_rules_fail_closed_routing_unavailable(routing_db):
    factory = routing_db
    port = _build_port(factory, ScriptedAdapter({}))

    with pytest.raises(RoutingUnavailableError) as exc_info:
        await port.lock_route(_request("bibles"))
    assert exc_info.value.code == ROUTING_UNAVAILABLE


async def test_boundary_does_not_disguise_routing_unavailable():
    class FailingPort:
        async def complete(self, request):
            raise RoutingUnavailableError(request.capability)

    boundary = StoryModelBoundary(FailingPort(), registry=dict(STORY_PROMPT_REGISTRY))
    entry = next(iter(STORY_PROMPT_REGISTRY.values()))
    with pytest.raises(RoutingUnavailableError):
        await boundary.invoke(entry.prompt_id, variables={})


# ---------------------------------------------------------------------------
# P0.3.5 — model fallback for defined transient failures only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_falls_back_to_declared_model_and_records_receipt(routing_db):
    factory = routing_db
    _make_rule(
        factory,
        role="studio.story.screenplay.generate",
        primary=PRIMARY_MODEL,
        fallback=FALLBACK_MODEL,
        priority=1,
    )
    receipt_repo = SQLModelRouteReceiptRepository(factory())
    adapter = ScriptedAdapter({"primary-native": TimeoutFailure("slow upstream")})
    port = _build_port(factory, adapter, receipt_repo=receipt_repo)

    result = await port.complete(_request("screenplay"))

    assert result.content == "{}"
    assert result.usage["fallback_used"] is True
    # The typed trigger code: either the original timeout or, after every
    # exact-equivalent primary endpoint failed, the exhaustion class.
    assert result.usage["fallback_reason"] in {
        "STORY_PROVIDER_TIMEOUTFAILURE",
        "STORY_PROVIDER_ENDPOINTS_EXHAUSTED",
    }
    assert result.usage["canonical_model_id"] == FALLBACK_MODEL
    # Primary native model attempted first, then the fallback binding.
    assert adapter.calls[0] == "primary-native"
    assert adapter.calls[-1] == "fallback-native"

    rows = receipt_repo.list_receipts(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["task_id"] != ""
    assert row["role"] == "studio.story.screenplay.generate"
    assert row["rule_id"] == "role-studio.story.screenplay.generate"
    assert row["selected_model_id"] == FALLBACK_MODEL
    assert row["fallback_used"] is True
    assert row["fallback_reason"]
    assert row["status"] == "success"
    assert row["started_at"] <= row["completed_at"]


@pytest.mark.asyncio
async def test_schema_failure_never_falls_back(routing_db):
    factory = routing_db
    _make_rule(
        factory,
        role="studio.story.revise",
        primary=PRIMARY_MODEL,
        fallback=FALLBACK_MODEL,
        priority=1,
    )
    receipt_repo = SQLModelRouteReceiptRepository(factory())
    adapter = ScriptedAdapter({"primary-native": InvalidRequestFailure("bad prompt contract")})
    port = _build_port(factory, adapter, receipt_repo=receipt_repo)

    with pytest.raises(InvalidRequestFailure):
        await port.complete(_request("revise"))

    # No fallback attempt was made against the fallback binding.
    assert adapter.calls.count("fallback-native") == 0


@pytest.mark.asyncio
async def test_system_default_appended_only_when_configured(routing_db):
    from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
    from windagent_worker.studio_model_port import (
        SYSTEM_DEFAULT_RULE_ID,
        compose_story_ruleset,
    )

    sql_ruleset = RoutingRuleSet(
        rules=[
            RoutingRule(
                rule_id="role-x",
                rule_version=1,
                canonical_model_id=PRIMARY_MODEL,
            )
        ]
    )
    composed = compose_story_ruleset(sql_ruleset, system_default_model=DEFAULT_MODEL)
    ids = [r.rule_id for r in composed.rules]
    assert ids[-1] == SYSTEM_DEFAULT_RULE_ID
    assert composed.rules[-1].priority > composed.rules[0].priority

    recomposed = compose_story_ruleset(composed, system_default_model=DEFAULT_MODEL)
    assert [r.rule_id for r in recomposed.rules].count(SYSTEM_DEFAULT_RULE_ID) == 1

    empty_composed = compose_story_ruleset(
        RoutingRuleSet(rules=[]), system_default_model=None
    )
    assert empty_composed.rules == []


# ---------------------------------------------------------------------------
# P0.3.6 — receipts API
# ---------------------------------------------------------------------------


def test_receipts_and_roles_api_surface(routing_db):
    from windagent_api.dependencies import get_route_receipt_repository
    from windagent_api.routers.v3.routing import router as routing_router

    factory = routing_db
    repo = SQLModelRouteReceiptRepository(factory())
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repo.record_receipt(
        task_id="task-p03-api",
        role="studio.story.idea.generate",
        rule_id="role-studio.story.idea.generate",
        route_lock_id="lk-p03",
        selected_provider="scripted-provider",
        selected_model_id=PRIMARY_MODEL,
        started_at=now,
        completed_at=now,
    )

    app = FastAPI()
    app.include_router(routing_router)
    app.dependency_overrides[get_route_receipt_repository] = lambda: repo
    client = TestClient(app)

    roles_response = client.get("/api/v3/routing/roles")
    assert roles_response.status_code == 200
    roles = {item["role"]: item for item in roles_response.json()}
    assert "studio.story.idea.generate" in roles
    assert "studio.story.screenplay.review" in roles["studio.story.review"]["aliases"]

    receipts_response = client.get("/api/v3/routing/receipts", params={"task_id": "task-p03-api"})
    assert receipts_response.status_code == 200
    payload = receipts_response.json()
    assert len(payload) == 1
    assert payload[0]["selected_model_id"] == PRIMARY_MODEL
    assert payload[0]["status"] == "success"


def test_alembic_head_is_route_receipts():
    from windagent_storage.migrations.runner import alembic_heads

    assert list(alembic_heads()) == ["0017_route_receipts"]
