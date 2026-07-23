"""
WorkflowState enum and explicit transition matrix for WindAgent Orchestration V2.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set
from windagent_core.errors.exceptions import DomainError


class WorkflowState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_WORKFLOW_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.PENDING: {
        WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.FAILED, WorkflowState.CANCELLED
    },
    WorkflowState.RUNNING: {
        WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED
    },
    WorkflowState.PAUSED: {
        WorkflowState.RUNNING, WorkflowState.CANCELLED, WorkflowState.FAILED
    },
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
    WorkflowState.CANCELLED: set(),
}


class WorkflowStateMachine:
    @staticmethod
    def is_terminal(state: WorkflowState | str) -> bool:
        val = state.value if isinstance(state, Enum) else str(state)
        return val in ("completed", "failed", "cancelled")

    @staticmethod
    def can_transition(current: WorkflowState | str, target: WorkflowState | str) -> bool:
        curr_val = WorkflowState(current) if isinstance(current, str) else current
        targ_val = WorkflowState(target) if isinstance(target, str) else target
        if curr_val == targ_val:
            return True
        return targ_val in ALLOWED_WORKFLOW_TRANSITIONS.get(curr_val, set())

    @staticmethod
    def transition(current: WorkflowState | str, target: WorkflowState | str) -> WorkflowState:
        curr_val = WorkflowState(current) if isinstance(current, str) else current
        targ_val = WorkflowState(target) if isinstance(target, str) else target

        if not WorkflowStateMachine.can_transition(curr_val, targ_val):
            raise DomainError(
                message=f"Illegal workflow state transition from [{curr_val.value}] to [{targ_val.value}].",
                code="WINDAGENT_ERR_ILLEGAL_WORKFLOW_TRANSITION",
                details={"current_state": curr_val.value, "target_state": targ_val.value},
            )
        return targ_val
