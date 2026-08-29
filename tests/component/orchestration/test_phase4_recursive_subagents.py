"""Phase 4 durable recursive subagents — focused tests (ban_ke_hoach_v1)."""
from __future__ import annotations
import uuid
import pytest
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
from windagent_core.domain.agent_loop import AgentBudgetLimits, AgentLoopState
from windagent_core.domain.delegation import ChildFailurePolicy
from windagent_orchestration.agent_loop.budget_controller import AgentBudgetController
from windagent_orchestration.delegation.controller import DelegationController
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.agent_loop_repository import AgentLoopRepository
from windagent_storage.repositories.delegation_repository import DelegationRepository
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_context.compaction import ContextCompactor
def _new_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"
@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()
def delegation_controller(db: DatabaseManager) -> DelegationController:
    return DelegationController(session_factory=db.session_factory, delegation_repo_factory=lambda s: DelegationRepository(s), agent_loop_repo_factory=lambda s: AgentLoopRepository(s), multi_repo_factory=lambda s: MultiAgentRepository(s))
def budget_controller(db: DatabaseManager) -> AgentBudgetController:
    return AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s), multi_repo_factory=lambda s: MultiAgentRepository(s))
# Helper to simulate lease takeover without requiring execution_leases DDL details
async def _simulate_lease_takeover_noop():
    import asyncio
    await asyncio.sleep(0.01)
@pytest.mark.asyncio
async def test_parent_spawns_four_children_with_bounded_context(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    dc = delegation_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_child_agents=10, max_parallel_children=10, max_recursion_depth=3, max_turns=10))
    for subtask, reason, policy in [("Research A: investigate topic X", "research-a", ChildFailurePolicy.RETRY),("Research B: investigate topic Y", "research-b", ChildFailurePolicy.SKIP),("Script: draft story from research", "script", ChildFailurePolicy.PARTIAL_SUCCESS),("Critic: review script", "critic", ChildFailurePolicy.ESCALATE)]:
        handle = await dc.spawn_child(parent_agent_run_id=parent, goal="Create episode about AI agents", subtask=subtask, delegation_reason=reason, relevant_artifacts=[f"artifact-{reason}"], selected_memory=[{"key": f"mem-{reason}", "value": "curated"}], policy={"can_write": False}, skills=["research", "summarize"], requested_budget=AgentBudgetLimits(max_turns=100), failure_policy=policy)
        assert handle.child_agent_run_id
        assert handle.parent_agent_run_id == parent
        assert handle.root_agent_run_id == parent
        assert handle.delegation_depth == 1
        assert handle.delegation_reason == reason
        assert handle.failure_policy == policy
        assert handle.allocated_budget is not None
        assert handle.allocated_budget.max_turns == 10
    async with db.session_factory() as session:
        repo = DelegationRepository(session)
        rows = await repo.list_children(parent)
        assert len(rows) == 4
        for r in rows:
            assert r["parent_agent_run_id"] == parent
            assert r["root_agent_run_id"] == parent
            assert r["delegation_depth"] == 1
            assert r["allocated_budget"]["max_turns"] == 10
            assert r["bounded_context"] is not None
            ctx = r["bounded_context"]
            assert "goal" in ctx and "subtask" in ctx
            assert "workspace_root" not in ctx
    snap = await bc.get_snapshot(parent)
    assert snap.usage.child_agents_spawned == 4
@pytest.mark.asyncio
async def test_spawn_returns_handle_not_raw_output_and_results_flow_via_summary(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_child_agents=5))
    dc = delegation_controller(db)
    handle = await dc.spawn_child(parent_agent_run_id=parent, goal="Goal G", subtask="Task T", delegation_reason="reason", relevant_artifacts=["art-1"], selected_memory=[{"k": "v"}], policy={"p": 1}, skills=["s1"], failure_policy=ChildFailurePolicy.SKIP)
    rec = await dc.get_delegation(handle.child_agent_run_id)
    assert rec is not None
    assert rec.child_result_summary is None
    summary = await dc.publish_child_result(child_agent_run_id=handle.child_agent_run_id, summary_text="Structured summary of findings", artifact_refs=["artifact://out/ref1", "artifact://out/ref2"], status="completed", metrics={"tokens": 123})
    assert summary.summary_text == "Structured summary of findings"
    assert summary.artifact_refs == ("artifact://out/ref1", "artifact://out/ref2")
    collected = await dc.collect_child_summaries(parent)
    assert len(collected) == 1
    rec2 = await dc.get_delegation(handle.child_agent_run_id)
    assert rec2.child_result_summary["status"] == "completed"
@pytest.mark.asyncio
async def test_child_cannot_create_new_budget(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_tokens=50, max_cost_usd=1.0, max_turns=5))
    dc = delegation_controller(db)
    handle = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="S", delegation_reason="r", requested_budget=AgentBudgetLimits(max_tokens=1000, max_cost_usd=999, max_turns=100))
    assert handle.allocated_budget.max_tokens == 50
    assert handle.allocated_budget.max_cost_usd == 1.0
    assert handle.allocated_budget.max_turns == 5
    handle2 = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="S2", delegation_reason="r2", requested_budget=AgentBudgetLimits(max_turns=2))
    assert handle2.allocated_budget.max_turns == 2
@pytest.mark.asyncio
async def test_failure_policies_declared_and_applied(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits())
    dc = delegation_controller(db)
    for policy, expected in [(ChildFailurePolicy.RETRY, "retry_child"),(ChildFailurePolicy.REPLACE, "replace_child"),(ChildFailurePolicy.PARTIAL_SUCCESS, "partial_success_proceed"),(ChildFailurePolicy.SKIP, "skip_child"),(ChildFailurePolicy.ESCALATE, "escalate")]:
        child = _new_id("child")
        handle = await dc.spawn_child(parent_agent_run_id=parent, child_agent_run_id=child, goal="G", subtask="S", delegation_reason=f"reason-{policy.value}", failure_policy=policy)
        await dc.publish_child_result(child_agent_run_id=handle.child_agent_run_id, summary_text="failed", status="failed")
        result = await dc.apply_failure_policy(parent_agent_run_id=parent, child_agent_run_id=handle.child_agent_run_id, error="tool failed")
        assert result["action"] == expected
@pytest.mark.asyncio
async def test_fail_parent_policy(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value)
    dc = delegation_controller(db)
    handle = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="S", delegation_reason="crit", failure_policy=ChildFailurePolicy.FAIL_PARENT)
    await dc.publish_child_result(child_agent_run_id=handle.child_agent_run_id, summary_text="failed", status="failed")
    await dc.apply_failure_policy(parent_agent_run_id=parent, child_agent_run_id=handle.child_agent_run_id, error="critical")
    async with db.session_factory() as session:
        row = await AgentLoopRepository(session).get_loop_state(parent)
        assert row["state"] == "FAILED"
@pytest.mark.asyncio
async def test_restart_visibility(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value)
    dc1 = delegation_controller(db)
    handles = []
    for i in range(4):
        h = await dc1.spawn_child(parent_agent_run_id=parent, goal="G", subtask=f"subtask-{i}", delegation_reason=f"reason-{i}")
        handles.append(h)
    await dc1.publish_child_result(child_agent_run_id=handles[0].child_agent_run_id, summary_text="research A done", artifact_refs=["a1"], status="completed")
    await dc1.publish_child_result(child_agent_run_id=handles[1].child_agent_run_id, summary_text="research B done", artifact_refs=["b1"], status="completed")
    dc2 = delegation_controller(db)
    children = await dc2.list_children(parent)
    assert len(children) == 4
    summaries = await dc2.collect_child_summaries(parent)
    assert len(summaries) == 2
@pytest.mark.asyncio
async def test_parent_pause_child_continues(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value)
    dc = delegation_controller(db)
    handles = [await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Research A", delegation_reason="research-a"), await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Research B", delegation_reason="research-b")]
    await dc.pause_parent(parent, reason="awaiting review")
    async with db.session_factory() as session:
        row = await AgentLoopRepository(session).get_loop_state(parent)
        assert row["state"] == "PAUSED"
    await dc.publish_child_result(child_agent_run_id=handles[0].child_agent_run_id, summary_text="A done", status="completed")
    await dc.publish_child_result(child_agent_run_id=handles[1].child_agent_run_id, summary_text="B done", status="completed")
    await dc.resume_parent(parent)
    async with db.session_factory() as session:
        row = await AgentLoopRepository(session).get_loop_state(parent)
        assert row["state"] == "RUNNING"
    compactor = ContextCompactor()
    messages = [{"role": "user", "content": f"goal: G subtask-{i}"} for i in range(20)] + [{"role": "assistant", "content": "critical decision: choose Research A approach"}]
    compacted = compactor.compact_conversation(messages, max_keep_recent=4)
    assert any("SYSTEM SUMMARY" in m["content"] for m in compacted)
    children = await dc.list_children(parent)
    assert len(children) == 2
@pytest.mark.asyncio
async def test_lease_takeover(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_parallel_children=4))
    dc = delegation_controller(db)
    handles = []
    for reason in ["research-a", "research-b", "script", "critic"]:
        h = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask=f"subtask {reason}", delegation_reason=reason)
        handles.append(h)
    # Simulate lease expiry and takeover: new worker reclaims the parent's children.
    # The delegation rows are durable and must survive the takeover.
    await _simulate_lease_takeover_noop()
    # New controller instance simulating Worker B after takeover
    dc2 = delegation_controller(db)
    rec = await dc2.get_delegation(handles[0].child_agent_run_id)
    assert rec is not None
    # Child can still publish after takeover (fencing is handled at execution layer, delegation is independent)
    await dc2.publish_child_result(child_agent_run_id=handles[0].child_agent_run_id, summary_text="post-takeover", status="completed")
    all_children = await dc2.list_children(parent)
    assert len(all_children) == 4
@pytest.mark.asyncio
async def test_depth_enforcement(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_recursion_depth=2))
    dc = delegation_controller(db)
    h1 = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="level1", delegation_reason="r1")
    assert h1.delegation_depth == 1
    h2 = await dc.spawn_child(parent_agent_run_id=h1.child_agent_run_id, goal="G", subtask="level2", delegation_reason="r2")
    assert h2.delegation_depth == 2
    with pytest.raises(Exception):
        await dc.spawn_child(parent_agent_run_id=h2.child_agent_run_id, goal="G", subtask="level3", delegation_reason="r3")
@pytest.mark.asyncio
async def test_parent_aggregates(db):
    parent = _new_id("parent")
    bc = budget_controller(db)
    await bc.ensure_loop(parent, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_child_agents=10))
    dc = delegation_controller(db)
    a = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Research A", delegation_reason="research-a", failure_policy=ChildFailurePolicy.SKIP)
    b = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Research B", delegation_reason="research-b", failure_policy=ChildFailurePolicy.RETRY)
    s = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Script", delegation_reason="script", failure_policy=ChildFailurePolicy.PARTIAL_SUCCESS)
    c = await dc.spawn_child(parent_agent_run_id=parent, goal="G", subtask="Critic", delegation_reason="critic", failure_policy=ChildFailurePolicy.FAIL_PARENT)
    await dc.publish_child_result(child_agent_run_id=a.child_agent_run_id, summary_text="A findings", artifact_refs=["art-a"], status="completed")
    await dc.publish_child_result(child_agent_run_id=b.child_agent_run_id, summary_text="B failed", status="failed")
    await dc.apply_failure_policy(parent_agent_run_id=parent, child_agent_run_id=b.child_agent_run_id)
    await dc.publish_child_result(child_agent_run_id=s.child_agent_run_id, summary_text="partial", artifact_refs=["art-script"], status="completed")
    await dc.publish_child_result(child_agent_run_id=c.child_agent_run_id, summary_text="critic ok", artifact_refs=["art-critic"], status="completed")
    summaries = await dc.collect_child_summaries(parent)
    assert len(summaries) == 4
