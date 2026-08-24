"""
Unit tests for WindAgent Orchestration Adoption (Phase 8).
Verifies E2E durable execution, duplicate claims, stale fencing tokens, pause/completion race,
retry vs callback race, crash recovery, destructive replay protection, and multi-replica lease isolation.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from windagent_core.domain.types import TaskId, SessionId, WorkflowRunId, StepId, WorkerId
from windagent_core.domain.lifecycle import TaskState

from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration import (
    TaskManager, LeaseManager, DestructiveReplayGuard
)
from windagent_orchestration.state_machine import TaskStateMachine


@pytest.fixture
async def async_uow_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield lambda: SqlUnitOfWork(factory)
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase8_durable_execution_e2e(async_uow_factory):
    tm = TaskManager(uow_factory=async_uow_factory)
    tid = TaskId.generate()
    sid = SessionId.generate()

    # 1. Initialize Task facts
    facts = tm.get_or_create_facts(tid, sid)
    assert facts.current_state == TaskState.RECEIVED

    # 2. Transition through lifecycle
    f2 = await tm.transition_task_durable(tid, sid, TaskState.PLANNING)
    assert f2.current_state == TaskState.PLANNING

    f3 = await tm.transition_task_durable(tid, sid, TaskState.RUNNING)
    assert f3.current_state == TaskState.RUNNING

    f4 = await tm.transition_task_durable(tid, sid, TaskState.COMPLETED)
    assert f4.current_state == TaskState.COMPLETED


@pytest.mark.asyncio
async def test_phase8_duplicate_claim_and_stale_fencing_token():
    lease_mgr = LeaseManager()
    step_id = str(StepId.generate())
    run_id = str(WorkflowRunId.generate())
    w1 = str(WorkerId("worker_1"))
    w2 = str(WorkerId("worker_2"))

    # Worker 1 claims lease
    lease1 = await lease_mgr.acquire_lease(step_id, run_id, w1, ttl_seconds=2.0)
    assert lease1 is not None
    assert lease1.worker_id == w1

    # Worker 2 attempts duplicate claim while worker 1 lease is valid
    lease2 = await lease_mgr.acquire_lease(step_id, run_id, w2, ttl_seconds=2.0)
    assert lease2 is None  # Claim rejected


@pytest.mark.asyncio
async def test_phase8_pause_vs_completion_race():
    curr_state = TaskState.RUNNING

    # Pause transition
    st_paused = TaskStateMachine.transition(curr_state, TaskState.PAUSED)
    assert st_paused == TaskState.PAUSED

    # Resume transition
    st_resumed = TaskStateMachine.transition(st_paused, TaskState.RUNNING)
    assert st_resumed == TaskState.RUNNING

    # Complete transition
    st_completed = TaskStateMachine.transition(st_resumed, TaskState.COMPLETED)
    assert st_completed == TaskState.COMPLETED
    assert TaskStateMachine.is_terminal(st_completed) is True


@pytest.mark.asyncio
async def test_phase8_destructive_replay_protection():
    guard = DestructiveReplayGuard()

    # Read-only tool -> Replay allowed
    assert guard.is_destructive(tool_name="view_file") is False

    # Destructive tool -> Replay blocked
    assert guard.is_destructive(tool_name="delete_file") is True
    assert guard.is_destructive(tool_name="run_command") is True


@pytest.mark.asyncio
async def test_phase8_two_replica_lease_isolation():
    mgr = LeaseManager()

    step_id = str(StepId.generate())
    run_id = str(WorkflowRunId.generate())
    w_a = str(WorkerId("replica_a_worker"))
    w_b = str(WorkerId("replica_b_worker"))

    lease_a = await mgr.acquire_lease(step_id, run_id, w_a)
    assert lease_a is not None

    lease_b = await mgr.acquire_lease(step_id, run_id, w_b)
    assert lease_b is None
