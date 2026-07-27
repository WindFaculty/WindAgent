"""
Unit Tests for WindAgent Orchestration Engine (Phase 8):
- TaskStateMachine 15-state transition table & illegal transition rejection
- RetryPolicy error classification & exponential backoff computation
- TaskScheduler bounded concurrency, priority queue, and project lock
- StepDispatcher duplicate step dispatch prevention
- RecoveryManager crash reconciliation & protection against auto-replaying destructive tools
- DurableExecutionFacts derived UI status computation
"""

import pytest
import pytest_asyncio
from windagent_core.domain.types import TaskId, SessionId, StepId, EventId
from windagent_core.domain.models import WorkflowStep
from windagent_core.events.envelope import EventEnvelope
from windagent_core.errors.exceptions import DomainError, RetryableError, NonRetryableError
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration import (
    TaskState, TaskStateMachine, RetryPolicy,
    TaskScheduler, TaskPriority, StepDispatcher, CancellationManager,
    RecoveryManager, TaskManager
)
from windagent_orchestration.dispatcher import LeaseManager
from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter


@pytest_asyncio.fixture
async def in_memory_db():
    from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    await db_manager.create_tables(V2BaseORM.metadata)
    yield db_manager
    await db_manager.close()


def test_state_machine_transitions():
    sm = TaskStateMachine()

    # Valid transitions
    assert sm.can_transition(TaskState.RECEIVED, TaskState.CLASSIFYING)
    assert sm.can_transition(TaskState.RUNNING, TaskState.WAITING_PERMISSION)
    assert sm.can_transition(TaskState.RUNNING, TaskState.COMPLETED)

    assert sm.transition(TaskState.RUNNING, TaskState.VERIFYING) == TaskState.VERIFYING

    # Illegal transition: RECEIVED -> COMPLETED directly must be rejected
    with pytest.raises(DomainError, match="Illegal state transition"):
        sm.transition(TaskState.RECEIVED, TaskState.COMPLETED)

    # Terminal state cannot transition to anything
    with pytest.raises(DomainError, match=r"(Illegal state transition|Cannot transition terminal)"):
        sm.transition(TaskState.COMPLETED, TaskState.RUNNING)


def test_retry_policy_classification_and_backoff():
    policy = RetryPolicy(max_attempts=3, initial_delay_seconds=1.0, backoff_factor=2.0)

    # Error classification
    assert policy.should_retry(RetryableError("Network timeout"), attempt=1)
    assert not policy.should_retry(NonRetryableError("Fatal auth error"), attempt=1)
    assert not policy.should_retry(RetryableError("Network timeout"), attempt=3)  # Max attempts reached

    # Exponential backoff delay
    assert policy.compute_delay(1) == 1.0
    assert policy.compute_delay(2) == 2.0
    assert policy.compute_delay(3) == 4.0


def test_task_scheduler_concurrency_and_priority_locks():
    scheduler = TaskScheduler(max_concurrency=2)

    # Acquire slot 1 & 2
    assert scheduler.acquire_slot("task_1", project_id="proj_A")
    assert scheduler.acquire_slot("task_2", project_id="proj_B")

    # Slot 3 denied due to max concurrency = 2
    assert not scheduler.acquire_slot("task_3", project_id="proj_C")

    # Project lock test: proj_A already active
    scheduler.release_slot("task_1", project_id="proj_A")
    assert scheduler.acquire_slot("task_3", project_id="proj_A")  # Now proj_A is free

    # Priority queue
    scheduler.enqueue("task_low", priority=TaskPriority.LOW)
    scheduler.enqueue("task_high", priority=TaskPriority.HIGH)
    assert scheduler._queue[0].task_id == "task_high"


@pytest.mark.asyncio
async def test_step_dispatcher_duplicate_prevention(in_memory_db):
    lease_mgr = LeaseManager(uow_factory=in_memory_db.session_factory)
    dispatcher = StepDispatcher(lease_manager=lease_mgr, runtime_port=FakeRuntimeAdapter())
    step = WorkflowStep(id=StepId.generate(), order=1, name="Step 1", tool_name="read_file")
    run_id = "run_100"

    assert await dispatcher.dispatch_step(run_id, step)
    # Second dispatch with identical idempotency key is rejected
    assert not await dispatcher.dispatch_step(run_id, step)


def test_cancellation_manager():
    cm = CancellationManager()
    run_id = "run_200"

    assert not cm.is_cancelled(run_id)
    cm.request_cancellation(run_id)
    assert cm.is_cancelled(run_id)

    with pytest.raises(DomainError, match="cancelled"):
        cm.raise_if_cancelled(run_id)


@pytest.mark.asyncio
async def test_recovery_manager_protection_against_destructive_tools(in_memory_db):
    sid = SessionId.generate()

    # Record event stream containing an interrupted destructive tool call (e.g. write_file)
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        env = EventEnvelope(
            event_id=EventId.generate(),
            event_type="step.started",
            session_id=sid,
            sequence=1,
            payload={"tool_name": "write_file", "path": "critical_file.txt"},
        )
        await uow.events.append_event(env)
        await uow.commit()

    # RecoveryManager scans session events
    rec_manager = RecoveryManager(session_factory=in_memory_db.session_factory)
    results = await rec_manager.scan_and_reconcile_in_flight_runs(sid)

    assert len(results) == 1
    run_id, state, msg = results[0]
    # Destructive tool interrupted -> must be FAILED, NOT re-executed
    assert state == TaskState.FAILED
    assert "destructive tool" in msg.lower()


def test_durable_facts_and_derived_ui_status():
    sid = SessionId.generate()
    tid = TaskId.generate()
    tm = TaskManager()

    facts = tm.get_or_create_facts(tid, sid)
    assert facts.derive_ui_status() == "running"

    # Transition step-by-step through valid state transitions
    tm.transition_task(tid, sid, TaskState.PLANNING)
    tm.transition_task(tid, sid, TaskState.RUNNING)
    tm.transition_task(tid, sid, TaskState.WAITING_PERMISSION)
    assert facts.derive_ui_status() == "waiting_permission"

    tm.transition_task(tid, sid, TaskState.RUNNING)
    tm.transition_task(tid, sid, TaskState.VERIFYING)
    assert facts.derive_ui_status() == "verifying"

    tm.transition_task(tid, sid, TaskState.COMPLETED)
    assert facts.derive_ui_status() == "completed"
