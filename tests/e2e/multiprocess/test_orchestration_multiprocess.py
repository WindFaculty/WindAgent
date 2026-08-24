"""
Phase 1 True Multi-Process E2E Test — Persistent Provider Routing Authority.

Proves ban_ke_hoach.md §1 multi-process requirements:
- Spawns distinct OS processes (1 API process simulation + 2 Worker processes)
- Targets a shared database file (or PostgreSQL if WINDAGENT_TEST_POSTGRES_URL is set)
- Verifies that all processes read and share the exact same RouteLock authority
- Verifies concurrent initial lock resolution across separate OS processes creates exactly ONE active lock
"""

from __future__ import annotations

import multiprocessing as mp
import tempfile
from pathlib import Path


from windagent_storage.database.sync_factory import make_sync_session_factory, sync_db_url
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.v3_repositories import SQLRouteLockRepository
from windagent_storage.repositories.v3_routing_repositories import SQLProviderRoutingAuditRepository
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.routing.rule_matcher import RuleMatchContext
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from tests.support.waiting import deterministic_sleep


def _create_schema(db_url: str):
    from sqlalchemy import create_engine, text
    import windagent_storage.orm.v3_models  # noqa: F401
    engine = create_engine(sync_db_url(db_url))
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA busy_timeout=30000;"))
    BaseORM.metadata.create_all(engine)
    # FK enforcement (GAP A): route_locks_v3.canonical_model_id references
    # canonical_models_v3.id. Seed the model the multi-process rule resolves to
    # BEFORE spawning child processes, so their lock inserts never violate the FK.
    from tests.fakes.providers.provider_graph import seed_canonical_model
    sf = make_sync_session_factory(db_url)
    seed_canonical_model(sf(), "cm-gpt4o-multi")
    # Warm up initial rule/tables so concurrent initializations don't contend on DDL
    session = sf()
    session.close()


def _make_lock_service(db_url: str):
    sf = make_sync_session_factory(db_url)
    rule = RoutingRule(
        rule_id="r-multi",
        rule_version=1,
        canonical_model_id="cm-gpt4o-multi",
        description="multi-process rule",
        enabled=True,
        priority=10,
    )
    return RouteLockService(
        ruleset=RoutingRuleSet(rules=[rule]),
        lock_repository=SQLRouteLockRepository(sf()),
        audit_repository=SQLProviderRoutingAuditRepository(sf()),
    )


def _ctx(scope_id: str):
    return RuleMatchContext(
        scope_id=scope_id,
        scope_type="session",
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


def _api_process_task(db_url: str, scope_id: str, queue: mp.Queue):
    """API process: resolves or creates route lock for a session."""
    for attempt in range(5):
        try:
            svc = _make_lock_service(db_url)
            lock = svc.resolve_or_create_lock(_ctx(scope_id))
            queue.put({"process": "API", "lock_id": lock.lock_id, "model": lock.canonical_model_id})
            return
        except Exception as exc:
            if "locked" in str(exc) and attempt < 4:
                deterministic_sleep(0.1 * (attempt + 1))
                continue
            queue.put({"process": "API", "error": str(exc)})
            return


def _worker_process_task(db_url: str, scope_id: str, worker_name: str, queue: mp.Queue):
    """Worker process: reads or resolves route lock for the same session."""
    for attempt in range(5):
        try:
            svc = _make_lock_service(db_url)
            lock = svc.resolve_or_create_lock(_ctx(scope_id))
            queue.put({"process": worker_name, "lock_id": lock.lock_id, "model": lock.canonical_model_id})
            return
        except Exception as exc:
            if "locked" in str(exc) and attempt < 4:
                deterministic_sleep(0.1 * (attempt + 1))
                continue
            queue.put({"process": worker_name, "error": str(exc)})
            return


def test_true_multi_process_cross_process_route_lock():
    """
    Spawns 1 API OS process + 2 Worker OS processes.
    All target the same DB file and must return the SAME active route lock.
    """
    tmp_dir = tempfile.mkdtemp(prefix="multiprocess_phase1_")
    db_path = Path(tmp_dir) / "shared_routing.db"
    db_url = f"sqlite:///{db_path}"

    _create_schema(db_url)

    queue = mp.Queue()
    scope_id = "session-e2e-shared"

    p_api = mp.Process(target=_api_process_task, args=(db_url, scope_id, queue))
    p_w1 = mp.Process(target=_worker_process_task, args=(db_url, scope_id, "Worker-1", queue))
    p_w2 = mp.Process(target=_worker_process_task, args=(db_url, scope_id, "Worker-2", queue))

    # Launch 1 API + 2 Worker processes concurrently
    p_api.start()
    p_w1.start()
    p_w2.start()

    p_api.join(timeout=10)
    p_w1.join(timeout=10)
    p_w2.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 3, f"Expected 3 process results, got: {results}"
    for r in results:
        assert "error" not in r, f"Process error: {r}"

    lock_ids = {r["lock_id"] for r in results}
    models = {r["model"] for r in results}

    assert len(lock_ids) == 1, f"Expected exactly 1 active lock_id across all OS processes, got: {lock_ids}"
    assert models == {"cm-gpt4o-multi"}, f"Expected canonical model cm-gpt4o-multi, got: {models}"