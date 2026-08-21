"""
Unit tests for WindAgent Core Canonical Lifecycle State Machines (Phase 3).
Verifies TaskState, WorkflowState, StepState, SessionState, transition matrices,
terminal state immutability, and optimistic concurrency versioning.
"""

import pytest
from datetime import timezone
from windagent_core.domain.lifecycle import (
    TaskState, WorkflowState, StepState, SessionState, TaskLifecycle, WorkflowLifecycle, StepLifecycle, SessionLifecycle, utc_now
)
from windagent_core.errors.exceptions import (
    InvalidStateTransitionError,
    TerminalStateMutationError,
    ConcurrentStateConflictError,
)


def test_utc_now_helper():
    now = utc_now()
    assert now.tzinfo is timezone.utc


def test_task_lifecycle_legal_flow():
    task_id = "task-101"
    v = 1

    # RECEIVED -> CLASSIFYING -> CONTEXT_BUILDING -> PLANNING -> READY -> RUNNING -> VERIFYING -> REVIEWING -> COMPLETED
    res1 = TaskLifecycle.transition(task_id, TaskState.RECEIVED, TaskState.CLASSIFYING, v)
    assert res1.to_state == TaskState.CLASSIFYING
    assert res1.new_version == 2

    res2 = TaskLifecycle.transition(task_id, TaskState.CLASSIFYING, TaskState.CONTEXT_BUILDING, 2)
    assert res2.to_state == TaskState.CONTEXT_BUILDING

    res3 = TaskLifecycle.transition(task_id, TaskState.CONTEXT_BUILDING, TaskState.PLANNING, 3)
    assert res3.to_state == TaskState.PLANNING

    res4 = TaskLifecycle.transition(task_id, TaskState.PLANNING, TaskState.READY, 4)
    assert res4.to_state == TaskState.READY

    res5 = TaskLifecycle.transition(task_id, TaskState.READY, TaskState.RUNNING, 5)
    assert res5.to_state == TaskState.RUNNING

    res6 = TaskLifecycle.transition(task_id, TaskState.RUNNING, TaskState.VERIFYING, 6)
    assert res6.to_state == TaskState.VERIFYING

    res7 = TaskLifecycle.transition(task_id, TaskState.VERIFYING, TaskState.REVIEWING, 7)
    assert res7.to_state == TaskState.REVIEWING

    res8 = TaskLifecycle.transition(task_id, TaskState.REVIEWING, TaskState.COMPLETED, 8)
    assert res8.to_state == TaskState.COMPLETED


def test_task_lifecycle_pause_resume():
    task_id = "task-102"
    # READY -> RUNNING -> PAUSED -> RUNNING
    TaskLifecycle.transition(task_id, TaskState.READY, TaskState.RUNNING, 1)
    res = TaskLifecycle.transition(task_id, TaskState.RUNNING, TaskState.PAUSED, 2)
    assert res.to_state == TaskState.PAUSED

    res2 = TaskLifecycle.transition(task_id, TaskState.PAUSED, TaskState.RUNNING, 3)
    assert res2.to_state == TaskState.RUNNING


def test_task_lifecycle_permission_retry_recovery():
    task_id = "task-103"
    # RUNNING -> WAITING_PERMISSION -> RUNNING
    TaskLifecycle.transition(task_id, TaskState.RUNNING, TaskState.WAITING_PERMISSION, 1)
    res = TaskLifecycle.transition(task_id, TaskState.WAITING_PERMISSION, TaskState.RUNNING, 2)
    assert res.to_state == TaskState.RUNNING

    # RUNNING -> RETRY_WAIT -> RUNNING
    TaskLifecycle.transition(task_id, TaskState.RUNNING, TaskState.RETRY_WAIT, 3)
    res2 = TaskLifecycle.transition(task_id, TaskState.RETRY_WAIT, TaskState.RUNNING, 4)
    assert res2.to_state == TaskState.RUNNING

    # RUNNING -> RECOVERING -> RUNNING
    TaskLifecycle.transition(task_id, TaskState.RUNNING, TaskState.RECOVERING, 5)
    res3 = TaskLifecycle.transition(task_id, TaskState.RECOVERING, TaskState.RUNNING, 6)
    assert res3.to_state == TaskState.RUNNING


def test_task_lifecycle_illegal_transition():
    with pytest.raises(InvalidStateTransitionError):
        TaskLifecycle.transition("task-104", TaskState.RECEIVED, TaskState.COMPLETED, 1)

    with pytest.raises(InvalidStateTransitionError):
        TaskLifecycle.transition("task-104", TaskState.READY, TaskState.VERIFYING, 1)


def test_task_lifecycle_terminal_immutability():
    terminals = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]
    for term in terminals:
        with pytest.raises(TerminalStateMutationError):
            TaskLifecycle.transition("task-105", term, TaskState.RUNNING, 1)


def test_workflow_lifecycle():
    wf_id = "wf-201"
    res1 = WorkflowLifecycle.transition(wf_id, WorkflowState.DRAFT, WorkflowState.READY, 1)
    assert res1.to_state == WorkflowState.READY

    res2 = WorkflowLifecycle.transition(wf_id, WorkflowState.READY, WorkflowState.RUNNING, 2)
    assert res2.to_state == WorkflowState.RUNNING

    res3 = WorkflowLifecycle.transition(wf_id, WorkflowState.RUNNING, WorkflowState.COMPLETED, 3)
    assert res3.to_state == WorkflowState.COMPLETED

    with pytest.raises(TerminalStateMutationError):
        WorkflowLifecycle.transition(wf_id, WorkflowState.COMPLETED, WorkflowState.RUNNING, 4)


def test_step_lifecycle():
    step_id = "step-301"
    # BLOCKED -> READY -> CLAIMED -> DISPATCHED -> RUNNING -> WAITING_PERMISSION -> RUNNING -> COMPLETED
    StepLifecycle.transition(step_id, StepState.BLOCKED, StepState.READY, 1)
    StepLifecycle.transition(step_id, StepState.READY, StepState.CLAIMED, 2)
    StepLifecycle.transition(step_id, StepState.CLAIMED, StepState.DISPATCHED, 3)
    StepLifecycle.transition(step_id, StepState.DISPATCHED, StepState.RUNNING, 4)
    StepLifecycle.transition(step_id, StepState.RUNNING, StepState.WAITING_PERMISSION, 5)
    StepLifecycle.transition(step_id, StepState.WAITING_PERMISSION, StepState.RUNNING, 6)
    res = StepLifecycle.transition(step_id, StepState.RUNNING, StepState.COMPLETED, 7)
    assert res.to_state == StepState.COMPLETED

    with pytest.raises(TerminalStateMutationError):
        StepLifecycle.transition(step_id, StepState.COMPLETED, StepState.RUNNING, 8)


def test_session_lifecycle():
    session_id = "sess-401"
    SessionLifecycle.transition(session_id, SessionState.IDLE, SessionState.ACTIVE, 1)
    SessionLifecycle.transition(session_id, SessionState.ACTIVE, SessionState.COMPLETED, 2)
    res = SessionLifecycle.transition(session_id, SessionState.COMPLETED, SessionState.ARCHIVED, 3)
    assert res.to_state == SessionState.ARCHIVED

    with pytest.raises(TerminalStateMutationError):
        SessionLifecycle.transition(session_id, SessionState.ARCHIVED, SessionState.ACTIVE, 4)


def test_optimistic_concurrency_conflict():
    task_id = "task-501"
    with pytest.raises(ConcurrentStateConflictError):
        TaskLifecycle.transition(
            aggregate_id=task_id,
            current=TaskState.RECEIVED,
            target=TaskState.CLASSIFYING,
            current_version=5,
            expected_version=4,  # Mismatch!
        )
