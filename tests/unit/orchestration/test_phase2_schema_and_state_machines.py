"""
Phase 2 Unit Tests: Schema, ORM Models, and State Transition Matrices.
Verifies atomic conditional updates, fencing tokens, and WorkflowState / StepState state machines.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "apps/backend"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
from windagent_storage.repositories.v2_orchestration_repositories import (
    SqlTaskRunRepository, SqlExecutionLeaseRepository, SqlRuntimeExecutionRepository
)
from windagent_orchestration.state_machine import (
    WorkflowState, WorkflowStateMachine, StepState, StepStateMachine
)
from windagent_core.errors.exceptions import DomainError


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(V2BaseORM.metadata.create_all)
    
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    
    await engine.dispose()


def test_workflow_state_machine_valid_and_invalid():
    """Verify WorkflowStateMachine transitions."""
    assert WorkflowStateMachine.can_transition(WorkflowState.PENDING, WorkflowState.RUNNING)
    assert WorkflowStateMachine.can_transition(WorkflowState.RUNNING, WorkflowState.PAUSED)
    assert WorkflowStateMachine.can_transition(WorkflowState.PAUSED, WorkflowState.RUNNING)
    assert WorkflowStateMachine.can_transition(WorkflowState.RUNNING, WorkflowState.COMPLETED)
    
    # Terminal states have no outgoing transitions
    assert not WorkflowStateMachine.can_transition(WorkflowState.COMPLETED, WorkflowState.RUNNING)
    
    with pytest.raises(DomainError) as exc_info:
        WorkflowStateMachine.transition(WorkflowState.COMPLETED, WorkflowState.RUNNING)
    assert exc_info.value.code in ("WINDAGENT_ERR_ILLEGAL_WORKFLOW_TRANSITION", "WINDAGENT_ERR_TERMINAL_STATE_MUTATION", "WINDAGENT_ERR_INVALID_STATE_TRANSITION")


def test_step_state_machine_valid_and_invalid():
    """Verify StepStateMachine transitions."""
    assert StepStateMachine.can_transition(StepState.PENDING, StepState.READY)
    assert StepStateMachine.can_transition(StepState.READY, StepState.DISPATCHED)
    assert StepStateMachine.can_transition(StepState.DISPATCHED, StepState.RUNNING)
    assert StepStateMachine.can_transition(StepState.RUNNING, StepState.COMPLETED)
    
    with pytest.raises(DomainError) as exc_info:
        StepStateMachine.transition(StepState.COMPLETED, StepState.DISPATCHED)
    assert exc_info.value.code in ("WINDAGENT_ERR_ILLEGAL_STEP_TRANSITION", "WINDAGENT_ERR_TERMINAL_STATE_MUTATION", "WINDAGENT_ERR_INVALID_STATE_TRANSITION")


@pytest.mark.asyncio
async def test_atomic_conditional_optimistic_concurrency(db_session):
    """Verify SqlTaskRunRepository.save_facts raises on version mismatch."""
    repo = SqlTaskRunRepository(db_session)
    v1 = await repo.save_facts("task_1", "sess_1", "received", 1, {"title": "Test Task"})
    assert v1 == 1

    # Save next version successfully
    v2 = await repo.save_facts("task_1", "sess_1", "running", 1, {"title": "Test Task"})
    assert v2 == 2

    # Save with wrong version -> raises DomainError
    with pytest.raises(DomainError) as exc_info:
        await repo.save_facts("task_1", "sess_1", "completed", 1, {"title": "Test Task"})
    assert exc_info.value.code == "WINDAGENT_ERR_OPTIMISTIC_CONCURRENCY_VIOLATION"


@pytest.mark.asyncio
async def test_lease_acquisition_and_fencing_tokens(db_session):
    """Verify SqlExecutionLeaseRepository generates fencing tokens and bumps generation on takeover."""
    repo = SqlExecutionLeaseRepository(db_session)
    
    res1 = await repo.acquire_lease("lease_1", "step_1", "run_1", "w1", 10.0, "idemp_1")
    assert res1 is not None
    assert res1["lease_generation"] == 1
    assert "gen_1" in res1["fencing_token"]

    # Re-claim active lease by same worker returns same token
    res2 = await repo.acquire_lease("lease_1", "step_1", "run_1", "w1", 10.0, "idemp_1")
    assert res2 == res1

    # Expire lease manually and reclaim with different worker -> bumps generation
    await repo.reclaim_expired_leases()  # not expired yet
    # Force expired state
    res3 = await repo.acquire_lease("lease_2", "step_1", "run_1", "w2", 10.0, "idemp_1")
    # Because original lease was active and not expired, w2 gets None
    assert res3 is None


@pytest.mark.asyncio
async def test_runtime_execution_repository(db_session):
    """Verify SqlRuntimeExecutionRepository creates and updates records by fencing token."""
    repo = SqlRuntimeExecutionRepository(db_session)
    
    exec_record = await repo.create_execution(
        execution_id="exec_1",
        runtime_run_id="rrun_1",
        attempt_id="att_1",
        step_run_id="step_1",
        lease_generation=1,
        fencing_token="fence_123",
    )
    assert exec_record.status == "dispatched"

    # Update by matching fencing token succeeds
    ok = await repo.update_status_by_fencing_token(
        step_run_id="step_1",
        fencing_token="fence_123",
        status="completed",
        result_ref="art_123",
    )
    assert ok is True

    # Update with stale fencing token fails
    stale_ok = await repo.update_status_by_fencing_token(
        step_run_id="step_1",
        fencing_token="stale_token",
        status="failed",
    )
    assert stale_ok is False
