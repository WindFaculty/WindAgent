"""
StepState enum and explicit transition matrix for WindAgent Orchestration V2.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set
from windagent_core.errors.exceptions import DomainError


class StepState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_STEP_TRANSITIONS: Dict[StepState, Set[StepState]] = {
    StepState.PENDING: {
        StepState.READY, StepState.CANCELLED, StepState.FAILED
    },
    StepState.READY: {
        StepState.DISPATCHED, StepState.CANCELLED, StepState.FAILED
    },
    StepState.DISPATCHED: {
        StepState.RUNNING, StepState.COMPLETED, StepState.FAILED, StepState.CANCELLED, StepState.RETRY_WAIT, StepState.WAITING_PERMISSION
    },
    StepState.RUNNING: {
        StepState.COMPLETED, StepState.FAILED, StepState.CANCELLED, StepState.RETRY_WAIT, StepState.WAITING_PERMISSION
    },
    StepState.WAITING_PERMISSION: {
        StepState.RUNNING, StepState.CANCELLED, StepState.FAILED
    },
    StepState.RETRY_WAIT: {
        StepState.READY, StepState.DISPATCHED, StepState.FAILED, StepState.CANCELLED
    },
    StepState.COMPLETED: set(),
    StepState.FAILED: {
        StepState.RETRY_WAIT, StepState.READY
    },
    StepState.CANCELLED: set(),
}


class StepStateMachine:
    @staticmethod
    def is_terminal(state: StepState | str) -> bool:
        val = state.value if isinstance(state, Enum) else str(state)
        return val in ("completed", "failed", "cancelled")

    @staticmethod
    def can_transition(current: StepState | str, target: StepState | str) -> bool:
        curr_val = StepState(current) if isinstance(current, str) else current
        targ_val = StepState(target) if isinstance(target, str) else target
        if curr_val == targ_val:
            return True
        return targ_val in ALLOWED_STEP_TRANSITIONS.get(curr_val, set())

    @staticmethod
    def transition(current: StepState | str, target: StepState | str) -> StepState:
        curr_val = StepState(current) if isinstance(current, str) else current
        targ_val = StepState(target) if isinstance(target, str) else target

        if not StepStateMachine.can_transition(curr_val, targ_val):
            raise DomainError(
                message=f"Illegal step state transition from [{curr_val.value}] to [{targ_val.value}].",
                code="WINDAGENT_ERR_ILLEGAL_STEP_TRANSITION",
                details={"current_state": curr_val.value, "target_state": targ_val.value},
            )
        return targ_val
