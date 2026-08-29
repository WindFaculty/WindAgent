"""Phase 2 durable loop & budget controller (ban_ke_hoach_v1 §7) — focused tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import windagent_storage.orm.agent_loop_models  # noqa: F401 ensure BaseORM registers loop table for create_all fallback

from windagent_core.domain.agent_loop import (
    AgentBudgetLimits,
    AgentLoopState,
    BudgetScope,
)
from windagent_orchestration.agent_loop.budget_controller import AgentBudgetController, BudgetExhaustedError
from windagent_orchestration.orchestrator_service import OrchestratorService, Subtask
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.agent_loop_repository import AgentLoopRepository
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_core.contracts.execution import ExecutionHandle, ExecutionRequest, ExecutionResult, RuntimeStatus, RuntimeStatusEnum
from windagent_execution.registry import ExecutionRuntimeRegistry
from types import SimpleNamespace


class FakeRouteLockService:
    def resolve_or_create_lock(self, context: object) -> object:
        return SimpleNamespace(
            lock_id=f"lock-{uuid.uuid4().hex}",
            canonical_model_id="windagent/local-agent",
            routing_snapshot=SimpleNamespace(rule_version=1, rule_id="test", reason="test"),
        )


class HoldingRuntime:
    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        return ExecutionHandle(
            handle_id=f"handle-{uuid.uuid4().hex}",
            runtime_run_id=f"runtime-{uuid.uuid4().hex}",
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )
    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        return RuntimeStatus(handle_id=handle.handle_id, status=RuntimeStatusEnum.RUNNING)
    async def cancel(self, handle: ExecutionHandle) -> None:
        return None
    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        return ExecutionResult(handle_id=handle.handle_id, step_run_id=handle.step_run_id, status=RuntimeStatusEnum.RUNNING)
    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return None


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase2.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_loop_state_legal_and_illegal_transitions(db: DatabaseManager):
    async with db.session_factory() as session:
        repo = AgentLoopRepository(session)
        run_id = f"run-{uuid.uuid4().hex}"
        row = await repo.ensure_loop_state(agent_run_id=run_id, default_state="CREATED", limits={}, scope="conversation")
        assert row["state"] == "CREATED"
        updated = await repo.transition_loop_state(agent_run_id=run_id, expected_version=1, target_state="READY")
        assert updated is not None and updated["state"] == "READY"
        from windagent_core.domain.agent_loop import AgentLoopLifecycle
        with pytest.raises(Exception):
            AgentLoopLifecycle.transition(agent_run_id=run_id, current="READY", target="WAITING_TOOL", current_version=2, expected_version=2)
        await session.commit()
    async with db.session_factory() as session:
        repo2 = AgentLoopRepository(session)
        row2 = await repo2.get_loop_state(run_id)
        assert row2["state"] == "READY"
        assert row2["version"] == 2


@pytest.mark.asyncio
async def test_cas_stale_write_rejected(db: DatabaseManager):
    async with db.session_factory() as session:
        repo = AgentLoopRepository(session)
        run_id = f"run-{uuid.uuid4().hex}"
        await repo.ensure_loop_state(agent_run_id=run_id, default_state="CREATED", limits={}, scope="conversation")
        await session.commit()
    async with db.session_factory() as session:
        repo = AgentLoopRepository(session)
        ok = await repo.transition_loop_state(agent_run_id=run_id, expected_version=1, target_state="READY")
        assert ok is not None
        stale = await repo.transition_loop_state(agent_run_id=run_id, expected_version=1, target_state="RUNNING")
        assert stale is None
        await session.commit()


@pytest.mark.asyncio
async def test_budget_turn_exhaustion_fail_closed(db: DatabaseManager):
    run_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s), multi_repo_factory=lambda s: MultiAgentRepository(s))
    await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_turns=1), scope=BudgetScope.CONVERSATION)
    snap = await controller.authorize_turn(run_id)
    assert snap is not None
    await controller.record_turn_tokens(run_id, tokens=5)
    with pytest.raises(BudgetExhaustedError) as exc:
        await controller.authorize_turn(run_id)
    assert "max_turns" in exc.value.reason or "terminal" in exc.value.reason
    async with db.session_factory() as session:
        repo = AgentLoopRepository(session)
        row = await repo.get_loop_state(run_id)
        assert row["state"] == "FAILED"
        assert row["exhaustion_reason"] == "max_turns_exhausted"


@pytest.mark.asyncio
async def test_budget_token_exhaustion(db: DatabaseManager):
    run_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s), multi_repo_factory=lambda s: MultiAgentRepository(s))
    await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_tokens=10), scope=BudgetScope.CONVERSATION)
    await controller.record_turn_tokens(run_id, tokens=8)
    snap = await controller.authorize_turn(run_id)
    assert snap.is_exhausted() is None
    await controller.record_turn_tokens(run_id, tokens=5)
    snap2 = await controller.get_snapshot(run_id)
    assert snap2.exhaustion_reason == "max_tokens_exhausted"


@pytest.mark.asyncio
async def test_budget_retry_exhaustion(db: DatabaseManager):
    run_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_retries=1))
    await controller.record_retry(run_id)
    snap = await controller.get_snapshot(run_id)
    assert snap.exhaustion_reason == "max_retries_exhausted"
    with pytest.raises(BudgetExhaustedError):
        await controller.authorize_turn(run_id)


@pytest.mark.asyncio
async def test_budget_wall_time_exhaustion(db: DatabaseManager):
    run_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_wall_time_seconds=1))
    async with db.session_factory() as session:
        await session.execute(text("UPDATE agent_loop_states SET started_at=:t WHERE agent_run_id=:id"), {"t": datetime.now(timezone.utc) - timedelta(seconds=2), "id": run_id})
        await session.commit()
    with pytest.raises(BudgetExhaustedError) as exc:
        await controller.authorize_turn(run_id)
    assert "wall_time" in exc.value.reason


@pytest.mark.asyncio
async def test_child_clamping_no_self_created_budget(db: DatabaseManager):
    parent_id = f"run-{uuid.uuid4().hex}"
    child_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    await controller.ensure_loop(parent_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_turns=2, max_tokens=100), scope=BudgetScope.CONVERSATION)
    child_snap = await controller.derive_child_budget(parent_id, child_id, requested_limits=AgentBudgetLimits(max_turns=10, max_tokens=1000, max_cost_usd=999))
    assert child_snap.limits.max_turns == 2
    assert child_snap.limits.max_tokens == 100
    child2_id = f"run-{uuid.uuid4().hex}"
    child2 = await controller.derive_child_budget(parent_id, child2_id, requested_limits=AgentBudgetLimits(max_turns=1))
    assert child2.limits.max_turns == 1
    parent_snap = await controller.get_snapshot(parent_id)
    assert parent_snap.usage.child_agents_spawned == 2


@pytest.mark.asyncio
async def test_parallel_child_limit_enforced(db: DatabaseManager):
    parent_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    await controller.ensure_loop(parent_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_parallel_children=1, max_child_agents=10))
    child1 = f"run-{uuid.uuid4().hex}"
    await controller.derive_child_budget(parent_id, child1, requested_limits=AgentBudgetLimits())
    child2 = f"run-{uuid.uuid4().hex}"
    with pytest.raises(BudgetExhaustedError) as exc:
        await controller.derive_child_budget(parent_id, child2, requested_limits=AgentBudgetLimits())
    assert "parallel" in exc.value.reason
    await controller.release_parallel_slot(parent_id)
    child3 = f"run-{uuid.uuid4().hex}"
    snap = await controller.derive_child_budget(parent_id, child3, requested_limits=AgentBudgetLimits())
    assert snap.agent_run_id == child3


@pytest.mark.asyncio
async def test_restart_reload_preserves_budgets_and_no_work_after_exhaustion(db: DatabaseManager):
    run_id = f"run-{uuid.uuid4().hex}"
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_turns=1))
    await controller.record_turn_tokens(run_id, tokens=1)
    new_controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s))
    with pytest.raises(BudgetExhaustedError):
        await new_controller.authorize_turn(run_id)


@pytest.mark.asyncio
async def test_provider_turn_respects_budget_via_orchestrator(db: DatabaseManager):
    runtime = HoldingRuntime()
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("local_agent", runtime)
    fake_lock = FakeRouteLockService()
    service = OrchestratorService(
        db.session_factory,
        registry,
        route_lock_service=fake_lock,
        repo_factory=lambda s: MultiAgentRepository(s),
        agent_loop_repo_factory=lambda s: AgentLoopRepository(s),
    )
    goal = await service.submit_goal(
        conversation_id=f"conv-{uuid.uuid4().hex}",
        objective="Test budget",
        subtasks=(Subtask(objective="do thing", node_id="n1"),),
    )
    agent = goal.agents[0]
    controller = AgentBudgetController(session_factory=db.session_factory, repo_factory=lambda s: AgentLoopRepository(s), multi_repo_factory=lambda s: MultiAgentRepository(s))
    run_id = agent.agent_run_id
    async with db.session_factory() as session:
        repo = AgentLoopRepository(session)
        cur = await repo.get_loop_state(run_id)
        if cur is not None:
            updated = await repo.replace_budget_limits(agent_run_id=run_id, expected_version=int(cur["version"]), limits=AgentBudgetLimits(max_turns=0).model_dump(), scope="conversation")
            assert updated is not None
            cur2 = await repo.get_loop_state(run_id)
            await repo.transition_loop_state(agent_run_id=run_id, expected_version=int(cur2["version"]), target_state=AgentLoopState.RUNNING.value)
        else:
            await controller.ensure_loop(run_id, initial_state=AgentLoopState.RUNNING.value, limits=AgentBudgetLimits(max_turns=0))
        await session.commit()
    async with db.session_factory() as session:
        await session.execute(text("UPDATE agent_runs SET status='running' WHERE agent_run_id=:id"), {"id": run_id})
        await session.execute(text("UPDATE task_node_runs SET state='running' WHERE task_node_run_id=(SELECT task_node_run_id FROM agent_runs WHERE agent_run_id=:id)"), {"id": run_id})
        await session.execute(text("UPDATE agent_sessions SET status='running' WHERE agent_session_id=(SELECT agent_session_id FROM agent_runs WHERE agent_run_id=:id)"), {"id": run_id})
        await session.execute(text("UPDATE agent_instances SET status='running' WHERE agent_instance_id=:id"), {"id": agent.agent_instance_id})
        await session.commit()
    from unittest.mock import AsyncMock
    service._provider_execution_coordinator = AsyncMock()
    with pytest.raises(RuntimeError, match="budget exhausted"):
        await service.execute_provider_turn(
            conversation_id=goal.conversation_id,
            agent_instance_id=agent.agent_instance_id,
            prompt="hello",
        )
    async with db.session_factory() as session:
        cnt = (await session.execute(text("SELECT COUNT(*) FROM agent_turns WHERE agent_run_id=:id"), {"id": run_id})).scalar_one()
        assert cnt == 0
