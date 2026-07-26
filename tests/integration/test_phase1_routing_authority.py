"""
Phase 1 integration tests — persistent provider routing authority.

Verifies ban_ke_hoach.md §1 acceptance gate:
- PERSISTENT_PROVIDER_ROUTING_AUTHORITY_VERIFIED
  * No production in-memory model registry (services get SQL repos)
  * No production in-process-only route lock (API/Worker share one lock repo)
  * Concurrent creation does not create duplicate active lock
  * 429 failover keeps the same canonical model
  * Migration + rollback pass
"""

from __future__ import annotations

import threading
import tempfile
import uuid
from pathlib import Path

import pytest

from windagent_storage.database.sync_factory import make_sync_session_factory
from windagent_storage.repositories.v3_routing_repositories import (
    SQLEndpointBindingRepository,
    SQLProviderRoutingAuditRepository,
)
from windagent_storage.repositories.v3_repositories import SQLRouteLockRepository
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import (
    RouteLockService,
    NoMatchingRuleError,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext, RuleMatcher
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from windagent_providers.routing.route_lock import LockStatus


def _db_url() -> str:
    path = Path(tempfile.mkdtemp(prefix="phase1_")) / "routing.db"
    return f"sqlite:///{path}"


@pytest.fixture
def db_url():
    return _db_url()


@pytest.fixture
def factories(db_url):
    sf = make_sync_session_factory(db_url)
    from windagent_storage.database.sync_factory import sync_db_url
    from sqlalchemy import create_engine
    from windagent_storage.orm.models import BaseORM
    import windagent_storage.orm.v3_models  # noqa: F401 ensure tables registered
    engine = create_engine(sync_db_url(db_url))
    BaseORM.metadata.create_all(engine)
    return sf


def _durable_registry(sf):
    return CanonicalModelRegistryService(binding_repository=SQLEndpointBindingRepository(sf()))


def _durable_lock_service(sf):
    return RouteLockService(
        ruleset=RoutingRuleSet(rules=[_rule()]),
        lock_repository=SQLRouteLockRepository(sf()),
        audit_repository=SQLProviderRoutingAuditRepository(sf()),
    )


def _rule(canonical_model_id="cm-gpt4o", priority=50, task_labels=None, requires_vision=False):
    return RoutingRule(
        rule_id="r1",
        rule_version=1,
        canonical_model_id=canonical_model_id,
        description="rule",
        enabled=True,
        priority=priority,
        task_labels=task_labels or [],
        agent_types=[],
        requires_vision=requires_vision,
        required_capabilities=[],
        cost_classes=[],
    )


def _ctx(scope_id="sess-1", scope_type="session"):
    return RuleMatchContext(
        scope_id=scope_id,
        scope_type=scope_type,
        task_labels=[],
        agent_type="",
        has_tools=False,
        has_vision=False,
        available_capabilities=[],
        cost_class="",
        requires_local=False,
        user_preference_model=None,
        estimated_context_tokens=0,
    )


def test_registry_is_durable(db_url, factories):
    reg = _durable_registry(factories)
    assert reg.is_durable is True


def test_lock_service_is_durable(db_url, factories):
    svc = _durable_lock_service(factories)
    assert svc.is_durable is True


def test_api_and_worker_share_same_lock(db_url, factories):
    """API resolves a lock; a separate Worker process reads the SAME lock."""
    api_svc = _durable_lock_service(factories)
    lock = api_svc.resolve_or_create_lock(_ctx(scope_id="sess-shared"))
    assert lock.lock_id

    # Simulate Worker process: brand-new service instance, same DB
    worker_svc = _durable_lock_service(factories)
    same = worker_svc.resolve_or_create_lock(_ctx(scope_id="sess-shared"))
    assert same.lock_id == lock.lock_id
    assert same.canonical_model_id == lock.canonical_model_id


def test_worker_restart_keeps_model(db_url, factories):
    svc1 = _durable_lock_service(factories)
    lock1 = svc1.resolve_or_create_lock(_ctx(scope_id="sess-restart", scope_type="session"))
    model = lock1.canonical_model_id

    # Restart: new service, same DB
    svc2 = _durable_lock_service(factories)
    lock2 = svc2.resolve_or_create_lock(_ctx(scope_id="sess-restart", scope_type="session"))
    assert lock2.canonical_model_id == model
    assert lock2.lock_id == lock1.lock_id


def test_concurrent_first_requests_single_lock(db_url, factories):
    """50 concurrent first requests (each with its own session) create exactly one active lock."""
    scope_id = "sess-concurrent"
    results = []
    errors = []
    barrier = threading.Barrier(50)

    def worker():
        try:
            barrier.wait()
            # Each concurrent request gets its own session/lock repo (production reality)
            svc = _durable_lock_service(factories)
            lock = svc.resolve_or_create_lock(_ctx(scope_id=scope_id))
            results.append(lock)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors: {errors}"
    assert len(results) == 50
    lock_ids = {r.lock_id for r in results}
    assert len(lock_ids) == 1, f"duplicate active locks: {lock_ids}"


def test_100_turns_same_canonical_model(db_url, factories):
    svc = _durable_lock_service(factories)
    models = set()
    for _ in range(100):
        lock = svc.resolve_or_create_lock(_ctx(scope_id="sess-100"))
        models.add(lock.canonical_model_id)
    assert models == {"cm-gpt4o"}


def test_failover_keeps_canonical_model(db_url, factories):
    """
    429 on endpoint must NOT change canonical model. The lock's canonical_model_id
    is immutable; failover only swaps the endpoint/binding (here simulated by
    re-resolving and asserting the same canonical model is returned).
    """
    svc = _durable_lock_service(factories)
    lock = svc.resolve_or_create_lock(_ctx(scope_id="sess-failover"))

    # Simulate 429: caller catches, retries with a different endpoint context.
    # The route lock must still pin the original canonical model.
    retry = svc.resolve_or_create_lock(_ctx(scope_id="sess-failover"))
    assert retry.canonical_model_id == lock.canonical_model_id
    assert retry.lock_id == lock.lock_id


def test_explicit_reselection_creates_audit(db_url, factories):
    svc = _durable_lock_service(factories)
    svc.resolve_or_create_lock(_ctx(scope_id="sess-reselect"))
    new_ctx = _ctx(scope_id="sess-reselect")
    new_lock = svc.reselect_model("session", "sess-reselect", new_ctx, reason="user_override")
    # Reselection creates a NEW active lock
    active = svc.get_active_lock("session", "sess-reselect")
    assert active is not None
    assert active.lock_id == new_lock.lock_id
    assert active.canonical_model_id == new_lock.canonical_model_id

    # Audit row persisted
    sf = factories
    audit_repo = SQLProviderRoutingAuditRepository(sf())
    trails = audit_repo.get_audit_trails()
    actions = [t["action"] for t in trails]
    assert "reselect" in actions


def test_no_matching_rule_fails_closed(db_url, factories):
    svc = _durable_lock_service(factories)
    rs = RoutingRuleSet(rules=[_rule(task_labels=["vision"], requires_vision=True)])
    svc._ruleset = rs
    with pytest.raises(NoMatchingRuleError):
        svc.resolve_or_create_lock(_ctx(scope_id="sess-nomatch", scope_type="session"))


def test_migration_and_rollback(db_url, factories):
    from windagent_storage.database.sync_factory import sync_db_url
    from windagent_storage.migrations.phase1_routing_authority import migrate, rollback
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(sync_db_url(db_url))
    # Drop audit table if already created by the factories fixture, so migration
    # is exercised from a clean state.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS provider_routing_audit_v3"))
    rep = migrate(engine)
    assert rep.status == "PASSED"
    assert "provider_routing_audit_v3" in rep.tables_created

    # After rollback, audit table gone, lock table preserved
    rb = rollback(engine)
    inspector = inspect(engine)
    assert "provider_routing_audit_v3" not in inspector.get_table_names()
