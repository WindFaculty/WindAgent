"""Phase 5 long-running hardening — Persistent Goal + Durable Checkpoints + Heartbeat (ban_ke_hoach_v1 §10)."""
from __future__ import annotations

import uuid
import pytest

import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
from windagent_core.domain.agent_loop import AgentLoopState
from windagent_core.domain.durable_checkpoint import CheckpointKind
from windagent_orchestration.agent_loop.budget_controller import AgentBudgetController
from windagent_orchestration.delegation.controller import DelegationController
from windagent_orchestration.long_running.checkpoint_service import CheckpointService
from windagent_orchestration.long_running.goal_service import GoalService
from windagent_orchestration.long_running.heartbeat import HeartbeatHardening
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.agent_loop_repository import AgentLoopRepository
from windagent_storage.repositories.agent_checkpoint_repository import AgentCheckpointRepository
from windagent_storage.repositories.delegation_repository import DelegationRepository
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_storage.repositories.persistent_goal_repository import PersistentGoalRepository


def _new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


def goal_service(db: DatabaseManager) -> GoalService:
    return GoalService(
        session_factory=db.session_factory,
        goal_repo_factory=lambda s: PersistentGoalRepository(s),
        multi_repo_factory=lambda s: MultiAgentRepository(s),
    )


def checkpoint_service(db: DatabaseManager) -> CheckpointService:
    return CheckpointService(
        session_factory=db.session_factory,
        checkpoint_repo_factory=lambda s: AgentCheckpointRepository(s),
        multi_repo_factory=lambda s: MultiAgentRepository(s),
    )


def budget_controller(db: DatabaseManager) -> AgentBudgetController:
    return AgentBudgetController(
        session_factory=db.session_factory,
        repo_factory=lambda s: AgentLoopRepository(s),
        multi_repo_factory=lambda s: MultiAgentRepository(s),
    )


def delegation_controller(db: DatabaseManager) -> DelegationController:
    return DelegationController(
        session_factory=db.session_factory,
        delegation_repo_factory=lambda s: DelegationRepository(s),
        agent_loop_repo_factory=lambda s: AgentLoopRepository(s),
        multi_repo_factory=lambda s: MultiAgentRepository(s),
    )


# ────────────────── Persistent Goal tests ──────────────────


@pytest.mark.asyncio
async def test_goal_create_and_progress(db):
    gs = goal_service(db)
    conv = _new_id("conv")
    # need conversation row for event FK — use repo helper
    async with db.session_factory() as session:
        await MultiAgentRepository(session).ensure_conversation(conv, "title")
        await session.commit()
    goal = await gs.create_goal(
        objective="Produce episode 042 about AI agents",
        completion_criteria={"episodes": 1, "quality": "high"},
        conversation_id=conv,
        parent_task_id=_new_id("parent"),
    )
    assert goal["goal_id"].startswith("goal_")
    assert goal["objective"] == "Produce episode 042 about AI agents"
    assert goal["status"] == "ACTIVE"
    assert goal["version"] == 1
    assert goal["completion_criteria"] == {"episodes": 1, "quality": "high"}
    assert goal["progress_summary"] == ""
    # transition to IN_PROGRESS
    g2 = await gs.mark_in_progress(goal["goal_id"])
    assert g2["status"] == "IN_PROGRESS"
    assert g2["version"] == 2
    g3 = await gs.update_progress(goal_id=goal["goal_id"], progress_summary="research 50% — 2 sources done")
    assert g3["progress_summary"] == "research 50% — 2 sources done"
    assert g3["last_progress_at"] is not None
    assert g3["version"] == 3


@pytest.mark.asyncio
async def test_goal_blocked_and_unblock_and_pause_resume(db):
    gs = goal_service(db)
    conv = _new_id("conv")
    async with db.session_factory() as s:
        await MultiAgentRepository(s).ensure_conversation(conv, None)
        await s.commit()
    g = await gs.create_goal(objective="Long goal", conversation_id=conv)
    await gs.mark_in_progress(g["goal_id"])
    blocked = await gs.block(g["goal_id"], blocked_reason="waiting_provider_approval")
    assert blocked["status"] == "BLOCKED"
    assert blocked["blocked_reason"] == "waiting_provider_approval"
    # cannot progress while blocked? progress still allowed? but terminal not — we allow progress while blocked (policy)
    unblocked = await gs.unblock(blocked["goal_id"])
    assert unblocked["status"] == "IN_PROGRESS"
    assert unblocked["blocked_reason"] is None
    paused = await gs.pause(unblocked["goal_id"], reason="human review")
    assert paused["status"] == "PAUSED"
    resumed = await gs.resume(paused["goal_id"])
    # PAUSED -> ACTIVE per transition matrix (ACTIVE after PAUSED)
    assert resumed["status"] in ("ACTIVE", "IN_PROGRESS")
    g_final = await gs.complete(resumed["goal_id"])
    assert g_final["status"] == "COMPLETED"
    # terminal cannot transition further
    with pytest.raises(Exception):
        await gs.update_progress(goal_id=g_final["goal_id"], progress_summary="should fail")
    with pytest.raises(Exception):
        await gs.block(g_final["goal_id"], blocked_reason="x")


@pytest.mark.asyncio
async def test_goal_lifecycle_illegal_and_terminal(db):
    gs = goal_service(db)
    g = await gs.create_goal(objective="goal illegal")
    # ACTIVE -> COMPLETED is legal
    g2 = await gs.complete(g["goal_id"])
    assert g2["status"] == "COMPLETED"
    # COMPLETED -> FAILED is illegal terminal
    with pytest.raises(Exception):
        await gs.fail(g["goal_id"], reason="no")
    # CAS conflict — stale version
    async with db.session_factory() as s:
        repo = PersistentGoalRepository(s)
        # version mismatch
        res = await repo.transition_status(goal_id=g2["goal_id"], expected_version=1, target_status="FAILED")
        assert res is None  # stale


@pytest.mark.asyncio
async def test_goal_restart_visibility(db):
    gs1 = goal_service(db)
    conv = _new_id("conv")
    async with db.session_factory() as s:
        await MultiAgentRepository(s).ensure_conversation(conv, None)
        await s.commit()
    g = await gs1.create_goal(objective="restart goal", conversation_id=conv)
    await gs1.mark_in_progress(g["goal_id"])
    await gs1.update_progress(goal_id=g["goal_id"], progress_summary="step 1 done")
    # new service instance after "worker restart" — same DB
    gs2 = goal_service(db)
    g2 = await gs2.get_goal(g["goal_id"])
    assert g2 is not None
    assert g2["progress_summary"] == "step 1 done"
    assert g2["status"] == "IN_PROGRESS"
    # continue progressing post-restart
    g3 = await gs2.update_progress(goal_id=g["goal_id"], progress_summary="step 2 after restart")
    assert g3["progress_summary"] == "step 2 after restart"


# ────────────────── Durable Checkpoint tests ──────────────────


@pytest.mark.asyncio
async def test_checkpoint_at_all_mandated_boundaries(db):
    agent = _new_id("agent")
    bc = budget_controller(db)
    await bc.ensure_loop(agent, initial_state=AgentLoopState.RUNNING.value)
    cs = checkpoint_service(db)
    kinds = [
        CheckpointKind.TURN_BOUNDARY.value,
        CheckpointKind.TOOL_BOUNDARY.value,
        CheckpointKind.CHILD_ADMISSION.value,
        CheckpointKind.CHILD_COMPLETION.value,
        CheckpointKind.COMPACTION.value,
        CheckpointKind.EXTERNAL_WAIT.value,
        CheckpointKind.TERMINAL_STATE.value,
    ]
    for kind in kinds:
        row = await cs.checkpoint(agent_run_id=agent, kind=kind, snapshot={"step": kind, "tokens": 123})
        assert row["kind"] == kind
        assert row["snapshot"]["step"] == kind
    # also convenience helpers
    await cs.at_turn_boundary(agent, snapshot={"k": "turn2"})
    await cs.at_tool_boundary(agent, snapshot={"k": "tool2"}, tool_name="search")
    await cs.at_child_admission(agent, snapshot={"k": "admit"})
    await cs.at_child_completion(agent, snapshot={"k": "complete"})
    await cs.at_compaction(agent, snapshot={"k": "compact"})
    await cs.at_external_wait(agent, snapshot={"k": "wait"})
    await cs.at_terminal_state(agent, snapshot={"k": "term"})
    rows = await cs.list_checkpoints(agent)
    assert len(rows) == 14
    # sequence deterministic and ordered
    seqs = [int(r["sequence"]) for r in rows]
    assert seqs == list(range(14))
    # per-kind filter
    turns = await cs.list_checkpoints(agent, kind=CheckpointKind.TURN_BOUNDARY.value)
    assert len(turns) == 2


@pytest.mark.asyncio
async def test_checkpoint_immutability_and_json_serializable(db):
    agent = _new_id("agent")
    cs = checkpoint_service(db)
    snap = {"history": [{"turn": 1}], "opaque": {"nested": [1, 2, 3]}}
    row = await cs.checkpoint(agent_run_id=agent, kind="turn_boundary", snapshot=snap)
    # mutating returned snapshot does not affect stored
    row["snapshot"]["history"].append({"turn": 999})
    row["snapshot"]["opaque"]["nested"].append(999)
    fetched = await cs.get_checkpoint(row["checkpoint_id"])
    assert fetched is not None
    assert len(fetched["snapshot"]["history"]) == 1
    assert fetched["snapshot"]["opaque"]["nested"] == [1, 2, 3]
    # mutating input after call does not affect store (deep-copy)
    snap["history"].append({"turn": 777})
    fetched2 = await cs.get_checkpoint(row["checkpoint_id"])
    assert len(fetched2["snapshot"]["history"]) == 1
    # non-serializable snapshot rejected
    with pytest.raises(Exception):
        await cs.checkpoint(agent_run_id=agent, kind="turn_boundary", snapshot={"bad": {1, 2, 3}})  # set not json


@pytest.mark.asyncio
async def test_checkpoint_no_host_authority_and_sanitize(db):
    agent = _new_id("agent")
    cs = checkpoint_service(db)
    # forbidden keys must be rejected
    for forbidden in ["provider_credentials", "credentials", "api_key", "secret", "provider_call", "schedule", "memory_write", "learning_promotion", "host_authority"]:
        with pytest.raises(Exception):
            await cs.checkpoint(agent_run_id=agent, kind="manual", snapshot={forbidden: "leak", "ok": 1})
        with pytest.raises(Exception):
            await cs.checkpoint(agent_run_id=agent, kind="tool_boundary", snapshot={"nested": {forbidden: "leak"}})
    # defense-in-depth: manually poisoned row is sanitized on direct repo path?
    # repository itself also rejects — verify sanitization helper strips when called directly
    from windagent_core.domain.durable_checkpoint import sanitize_snapshot

    poisoned = {"ok": 1, "secret": "leak", "nested": {"api_key": "k", "deep": {"provider_credentials": "x"}}}
    cleaned = sanitize_snapshot(poisoned)
    assert "secret" not in cleaned
    assert "api_key" not in cleaned["nested"]
    assert cleaned["ok"] == 1


@pytest.mark.asyncio
async def test_checkpoint_checkpointed_at_loop_version(db):
    agent = _new_id("agent")
    bc = budget_controller(db)
    await bc.ensure_loop(agent, initial_state=AgentLoopState.RUNNING.value)
    cs = checkpoint_service(db)
    r1 = await cs.checkpoint(agent_run_id=agent, kind="turn_boundary", snapshot={"v": 1})
    assert r1["loop_version_at_checkpoint"] >= 1
    # bump loop version via budget update
    await bc.record_turn_tokens(agent, tokens=10)
    r2 = await cs.checkpoint(agent_run_id=agent, kind="turn_boundary", snapshot={"v": 2})
    assert int(r2["loop_version_at_checkpoint"]) >= int(r1["loop_version_at_checkpoint"])
    assert int(r2["sequence"]) == int(r1["sequence"]) + 1


@pytest.mark.asyncio
async def test_checkpoint_restart_visibility_and_lease_takeover(db):
    agent = _new_id("agent")
    bc = budget_controller(db)
    await bc.ensure_loop(agent, initial_state=AgentLoopState.RUNNING.value)
    cs1 = checkpoint_service(db)
    await cs1.at_turn_boundary(agent, snapshot={"turn": 1})
    await cs1.at_tool_boundary(agent, snapshot={"tool": "search"}, tool_name="search")
    # new service after restart
    cs2 = checkpoint_service(db)
    rows = await cs2.list_checkpoints(agent)
    assert len(rows) == 2
    # lease takeover simulation: checkpoints survive independent of lease
    await cs2.at_child_admission(agent, snapshot={"child": "new"})
    rows2 = await cs2.list_checkpoints(agent)
    assert len(rows2) == 3
    latest = await cs2.latest_checkpoint(agent)
    assert latest["kind"] == CheckpointKind.CHILD_ADMISSION.value


@pytest.mark.asyncio
async def test_parent_pause_checkpoint_continues_and_survives_compaction(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    dc = delegation_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value)
    cs = checkpoint_service(db)
    await cs.at_turn_boundary(parent, snapshot={"msg": "before pause"})
    # durable parent goal mirrors agent pause semantics
    gs = goal_service(db)
    conv = _new_id("conv")
    async with db.session_factory() as s:
        await MultiAgentRepository(s).ensure_conversation(conv, None)
        await s.commit()
    goal = await gs.create_goal(objective="ep hardening", conversation_id=conv, agent_run_id=parent)
    await gs.mark_in_progress(goal["goal_id"])
    # spawn child and pause parent — child checkpoint must still succeed
    h = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Research A", delegation_reason="research-a")
    await dc.pause_parent(parent, reason="review")
    # child can still checkpoint
    child = h.child_agent_run_id
    await bc.ensure_loop(child, initial_state=AgentLoopState.RUNNING.value)
    await cs.at_turn_boundary(child, snapshot={"child_turn": 1})
    # parent can also still checkpoint while paused (compaction boundary)
    await cs.at_compaction(parent, snapshot={"compacted": True})
    await dc.resume_parent(parent)
    rows_parent = await cs.list_checkpoints(parent)
    rows_child = await cs.list_checkpoints(child)
    assert len(rows_parent) == 2
    assert len(rows_child) == 1


@pytest.mark.asyncio
async def test_kill_scenarios_deterministic_state_after_restart(db):
    """Kill UI/API/Worker/network at each stage — state deterministic after restart (§10 acceptance)."""
    gs = goal_service(db)
    conv = _new_id("conv")
    async with db.session_factory() as s:
        await MultiAgentRepository(s).ensure_conversation(conv, None)
        await s.commit()
    goal = await gs.create_goal(objective="deterministic recovery", conversation_id=conv)
    agent = _new_id("agent")
    bc = budget_controller(db)
    await bc.ensure_loop(agent, initial_state=AgentLoopState.RUNNING.value)
    cs = checkpoint_service(db)

    # stage 1: turn boundary
    await cs.at_turn_boundary(agent, snapshot={"stage": "turn", "turn": 1})
    await gs.mark_in_progress(goal["goal_id"])
    await gs.update_progress(goal_id=goal["goal_id"], progress_summary="turn 1 done")

    # simulate worker crash — new service instances with same DB
    gs2 = goal_service(db)
    cs2 = checkpoint_service(db)

    # state after crash is exactly the durable rows, no duplication, no loss
    g_after = await gs2.get_goal(goal["goal_id"])
    assert g_after["status"] == "IN_PROGRESS"
    assert g_after["progress_summary"] == "turn 1 done"
    cks = await cs2.list_checkpoints(agent)
    assert len(cks) == 1

    # stage 2: tool boundary + child admission
    await cs2.at_tool_boundary(agent, snapshot={"stage": "tool", "tool": "search"}, tool_name="search")
    dc = delegation_controller(db)
    h = await dc.spawn_child(parent_agent_run_id=agent, goal="G", subtask="child work", delegation_reason="child-a")
    await cs2.at_child_admission(agent, snapshot={"child": h.child_agent_run_id})
    # simulate network partition — new handles but same durable state
    cs3 = checkpoint_service(db)
    await cs3.at_child_completion(agent, snapshot={"child_done": h.child_agent_run_id})
    await cs3.at_compaction(agent, snapshot={"compaction": "summary"})
    await cs3.at_external_wait(agent, snapshot={"wait": "provider"})
    await cs3.at_terminal_state(agent, snapshot={"terminal": True})
    # deterministic final count: turn + tool + admission + completion + compaction + wait + terminal = 7
    final_cks = await cs3.list_checkpoints(agent)
    assert len(final_cks) == 7
    seqs = [int(r["sequence"]) for r in final_cks]
    assert seqs == list(range(7))
    kinds = [r["kind"] for r in final_cks]
    assert kinds == [
        CheckpointKind.TURN_BOUNDARY.value,
        CheckpointKind.TOOL_BOUNDARY.value,
        CheckpointKind.CHILD_ADMISSION.value,
        CheckpointKind.CHILD_COMPLETION.value,
        CheckpointKind.COMPACTION.value,
        CheckpointKind.EXTERNAL_WAIT.value,
        CheckpointKind.TERMINAL_STATE.value,
    ]
    # goal still consistent
    g_final = await gs2.get_goal(goal["goal_id"])
    assert g_final["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_heartbeat_two_roles_observability_and_liveness(db):
    # Observability: history records every tick with correct active_leases
    hb = HeartbeatHardening(worker_id="wkr_test", runtime_run_id="run_test1")
    r1 = await hb.heartbeat_tick(active_leases=0)
    assert r1.recorded.active_leases == 0
    assert r1.lease_renewed is None
    assert not r1.fencing_rejected
    r2 = await hb.heartbeat_tick(active_leases=1)
    assert r2.recorded.active_leases == 1
    assert len(hb.history) == 2
    snap = hb.determinism_snapshot()
    assert snap["ticks"] == 2
    assert snap["cancelled_count"] == 0

    # Liveness: fencing mismatch -> renewal False -> cancelled
    class FakeLease:
        def renew_lease(self, task_id, worker_id, fencing_token=None):
            return False  # stale token

    cancelled = []

    def on_cancel():
        cancelled.append(1)

    hb2 = HeartbeatHardening(
        worker_id="wkr_fence",
        runtime_run_id="run_f2",
        lease_manager=FakeLease(),
        current_task_provider=lambda: ("task-1", "fence_old"),
        cancellation_hook=on_cancel,
    )
    r3 = await hb2.heartbeat_tick()
    assert r3.fencing_rejected is True
    assert r3.cancelled is True
    assert hb2.cancelled_count == 1
    assert len(cancelled) == 1
    # success renewal does not cancel
    class OKLease:
        def renew_lease(self, task_id, worker_id, fencing_token=None):
            return True

    hb3 = HeartbeatHardening(
        worker_id="wkr_ok",
        lease_manager=OKLease(),
        current_task_provider=lambda: ("task-2", "fence_ok"),
    )
    r4 = await hb3.heartbeat_tick()
    assert r4.fencing_rejected is False
    assert r4.cancelled is False
    assert hb3.cancelled_count == 0
