"""Phase 4 — Focused Authority Tests for RoutingAuthorityBridge and Model Routing (P4-R4A / P4-R4B).

Validates:
1. RoutingAuthorityBridge._rule_to_routing_rule faithfully maps all predicates and versioning.
2. RoutingAuthorityBridge.refresh_ruleset syncs SQL rules into RouteLockService.
3. refresh_ruleset on empty SQL ruleset restores the captured deployment
   fallback (never an empty ruleset, never a stale deleted API rule).
4. Full API CRUD on routing rules triggers bridge refresh and keeps RouteLockService in sync.
5. simulate_route_decision routes through composed RouteLockService and creates durable SQL locks.
6. get_route_lock audits locks through RouteLockService (SQLRouteLockRepository).
7. Version conflict / optimistic concurrency on rule updates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.lifespan import lifespan
from windagent_api.routers.v3 import v3_router
from windagent_api.services.routing_authority_bridge import RoutingAuthorityBridge
from windagent_api.services.v3_demo_seed import NS_ROUTE_LOCKS, NS_ROUTING_RULES
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet


class InMemoryResourceService:
    """Minimal test double for V3ResourceService."""

    def __init__(self, initial_rules: list[dict[str, Any]] | None = None) -> None:
        self._rules: dict[str, dict[str, Any]] = {
            r["id"]: dict(r) for r in (initial_rules or [])
        }

    async def list(self, namespace: str) -> list[dict[str, Any]]:
        if namespace == NS_ROUTING_RULES:
            return list(self._rules.values())
        return []

    async def get(self, namespace: str, resource_id: str) -> dict[str, Any] | None:
        if namespace == NS_ROUTING_RULES:
            return self._rules.get(resource_id)
        return None

    def set_rules(self, rules: list[dict[str, Any]]) -> None:
        self._rules = {r["id"]: dict(r) for r in rules}


class InMemoryLockRepo:
    def __init__(self) -> None:
        self._locks: dict[str, dict[str, Any]] = {}

    def get_lock(self, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        for lock in self._locks.values():
            if lock["scope_type"] == scope_type and lock["scope_id"] == scope_id:
                return lock
        return None

    def get_lock_by_id(self, lock_id: str) -> dict[str, Any] | None:
        return self._locks.get(lock_id)

    def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: dict[str, Any],
        policy_version: int = 1,
    ) -> dict[str, Any]:
        lock_id = f"lock-{len(self._locks) + 1}"
        record = {
            "lock_id": lock_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "canonical_model_id": canonical_model_id,
            "routing_snapshot": routing_snapshot,
            "policy_version": policy_version,
            "status": "ACTIVE",
            "created_at": 1700000000.0,
            "updated_at": 1700000000.0,
        }
        self._locks[lock_id] = record
        return record

    def release_lock(self, lock_id: str) -> bool:
        if lock_id in self._locks:
            self._locks[lock_id]["status"] = "RELEASED"
            return True
        return False


def test_rule_to_routing_rule_mapping():
    """All rule predicates and metadata are faithfully mapped."""
    raw_rule: Dict[str, Any] = {
        "id": "rule-deepseek-code",
        "version": 3,
        "canonical_model_id": "deepseek/deepseek-coder",
        "description": "Primary coding rule",
        "enabled": True,
        "priority": 10,
        "task_labels": ["coding", "refactor"],
        "agent_types": ["Coder", "Developer"],
        "workflow_types": ["code_video"],
        "required_capabilities": ["code_exec"],
        "min_context_tokens": 8192,
        "requires_tools": True,
        "requires_vision": False,
        "cost_classes": ["standard"],
        "requires_local": False,
        "requires_private": False,
        "user_preference_model": "deepseek/deepseek-coder-v2",
    }

    mapped = RoutingAuthorityBridge._rule_to_routing_rule(raw_rule)
    assert mapped.rule_id == "rule-deepseek-code"
    assert mapped.rule_version == 3
    assert mapped.canonical_model_id == "deepseek/deepseek-coder"
    assert mapped.description == "Primary coding rule"
    assert mapped.enabled is True
    assert mapped.priority == 10
    assert mapped.task_labels == ["coding", "refactor"]
    assert mapped.agent_types == ["Coder", "Developer"]
    assert mapped.workflow_types == ["code_video"]
    assert mapped.required_capabilities == ["code_exec"]
    assert mapped.min_context_tokens == 8192
    assert mapped.requires_tools is True
    assert mapped.requires_vision is False
    assert mapped.cost_classes == ["standard"]
    assert mapped.requires_local is False
    assert mapped.requires_private is False
    assert mapped.user_preference_model == "deepseek/deepseek-coder-v2"


@pytest.mark.asyncio
async def test_refresh_ruleset_syncs_and_restores_fallback_on_empty_deletion():
    """refresh_ruleset syncs SQL rules and restores the deployment fallback when SQL is empty."""
    lock_repo = InMemoryLockRepo()
    fallback = RoutingRuleSet(
        rules=[
            RoutingRule(
                rule_id="orchestrator-local-agent",
                rule_version=1,
                canonical_model_id="windagent/local-agent",
                description="Phase-2 conversation control plane",
            )
        ]
    )
    lock_service = RouteLockService(
        ruleset=fallback,
        lock_repository=lock_repo,
    )
    resource_service = InMemoryResourceService(
        initial_rules=[
            {
                "id": "rule-1",
                "version": 1,
                "canonical_model_id": "anthropic/claude-3-5-sonnet",
                "priority": 10,
                "agent_types": ["Planner"],
            }
        ]
    )

    bridge = RoutingAuthorityBridge(
        resource_service=resource_service,  # type: ignore[arg-type]
        route_lock_service=lock_service,
    )

    # 1. Sync populated rules from SQL
    synced = await bridge.refresh_ruleset()
    assert len(synced.rules) == 1
    assert synced.rules[0].rule_id == "rule-1"
    assert len(lock_service.current_ruleset.rules) == 1
    assert lock_service.current_ruleset.rules[0].rule_id == "rule-1"

    # 2. Simulate deletion of all rules in SQL: the captured deployment
    #    fallback is restored — never an empty ruleset and never a stale
    #    deleted API rule.
    resource_service.set_rules([])
    restored = await bridge.refresh_ruleset()
    assert [r.rule_id for r in restored.rules] == ["orchestrator-local-agent"]
    assert [r.rule_id for r in lock_service.current_ruleset.rules] == [
        "orchestrator-local-agent"
    ]
    assert "rule-1" not in [r.rule_id for r in lock_service.current_ruleset.rules]


def _build_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(v3_router)
    return app


def test_routing_api_lifecycle_and_lock_audit(tmp_path: Path, monkeypatch):
    """Full HTTP test: Rule CRUD -> bridge refresh -> simulation -> lock audit."""
    db_path = tmp_path / "routing_authority.db"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("WINDAGENT_ENV", "test")
    monkeypatch.setenv("WINDAGENT_PROFILE", "test")

    app = _build_app()
    with TestClient(app) as client:
        container = app.state.container
        lock_service = container.route_lock_service

        # Seed the referenced canonical models in SQL so foreign key constraint
        # in route_locks_v3 is satisfied (the API rule model and the deployment
        # fallback model).
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.orm.v3_models import CanonicalModelV3ORM, ProviderVendorORM
        sync_factory = make_sync_session_factory(container.db_url)
        with sync_factory() as session:
            vendor = ProviderVendorORM(id="anthropic", name="Anthropic", vendor_type="cloud")
            session.merge(vendor)
            cm = CanonicalModelV3ORM(
                id="anthropic/claude-3-5-sonnet",
                vendor="anthropic",
                family="claude",
                canonical_name="claude-3-5-sonnet",
            )
            session.merge(cm)
            local_cm = CanonicalModelV3ORM(
                id="windagent/local-agent",
                vendor="windagent",
                family="local-agent",
                canonical_name="local-agent",
            )
            session.merge(local_cm)
            session.commit()

        # 1. Fresh start: no routing rules
        res = client.get("/api/v3/routing/rules")
        assert res.status_code == 200
        assert res.json() == []

        # 2. Create rule
        create_res = client.post(
            "/api/v3/routing/rules",
            json={
                "id": "rule-test-coder",
                "name": "Test Coder Rule",
                "canonical_model_id": "anthropic/claude-3-5-sonnet",
                "priority": 10,
                "agent_types": ["Coder"],
                "requires_tools": True,
            },
        )
        assert create_res.status_code == 201, create_res.text
        rule_data = create_res.json()
        assert rule_data["id"] == "rule-test-coder"
        assert rule_data["version"] == 1

        # Verify bridge immediately synced into RouteLockService
        assert len(lock_service.current_ruleset.rules) == 1
        assert lock_service.current_ruleset.rules[0].rule_id == "rule-test-coder"

        # 3. Simulate routing decision for 'Coder'
        sim_res = client.post(
            "/api/v3/routing/simulations",
            json={
                "role": "Coder",
                "requires_tools": True,
            },
        )
        assert sim_res.status_code == 200, sim_res.text
        decision = sim_res.json()
        assert decision["rule_id"] == "rule-test-coder"
        assert decision["canonical_model_id"] == "anthropic/claude-3-5-sonnet"
        lock_id = decision["route_lock_id"]
        assert lock_id

        # 4. Audit route lock through /api/v3/routing/locks/{lock_id}
        lock_res = client.get(f"/api/v3/routing/locks/{lock_id}")
        assert lock_res.status_code == 200, lock_res.text
        lock_detail = lock_res.json()
        assert lock_detail["lock_id"] == lock_id
        assert lock_detail["canonical_model_id"] == "anthropic/claude-3-5-sonnet"
        assert lock_detail["routing_snapshot"]["rule_id"] == "rule-test-coder"

        # 5. Audit nonexistent lock returns 404
        bad_lock = client.get("/api/v3/routing/locks/nonexistent-lock-id")
        assert bad_lock.status_code == 404

        # 6. Update rule with optimistic version check
        patch_res = client.patch(
            "/api/v3/routing/rules/rule-test-coder",
            json={
                "priority": 5,
                "expected_version": 1,
            },
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["version"] == 2
        assert patch_res.json()["priority"] == 5

        # Version conflict check
        conflict_res = client.patch(
            "/api/v3/routing/rules/rule-test-coder",
            json={
                "priority": 1,
                "expected_version": 1,  # Stale version
            },
        )
        assert conflict_res.status_code == 409

        # 7. Delete rule
        del_res = client.delete("/api/v3/routing/rules/rule-test-coder")
        assert del_res.status_code == 200
        assert del_res.json() == {"deleted": True, "id": "rule-test-coder"}

        # The deleted API rule is absent from the durable authority.
        gone = client.get("/api/v3/routing/rules/rule-test-coder")
        assert gone.status_code == 404

        # Only the original deployment fallback projection remains; the
        # deleted API rule is never retained in the runtime ruleset.
        assert [r.rule_id for r in lock_service.current_ruleset.rules] == [
            "orchestrator-local-agent"
        ]

        # 8. Simulation now succeeds through the deployment fallback.
        sim_fallback = client.post(
            "/api/v3/routing/simulations",
            json={"role": "Coder"},
        )
        assert sim_fallback.status_code == 200, sim_fallback.text
        fallback_decision = sim_fallback.json()
        assert fallback_decision["rule_id"] == "orchestrator-local-agent"
        assert fallback_decision["canonical_model_id"] == "windagent/local-agent"
        fallback_lock_id = fallback_decision["route_lock_id"]
        assert fallback_lock_id

        # The fallback lock is a dedicated route lock: it exists through
        # RouteLockService (dedicated route_locks_v3 table) and is absent from
        # the generic v3_resources:route_locks namespace.
        assert lock_service.get_lock_by_id(fallback_lock_id) is not None
        import asyncio

        assert (
            asyncio.run(
                container.v3_resource_service.get(NS_ROUTE_LOCKS, fallback_lock_id)
            )
            is None
        )
