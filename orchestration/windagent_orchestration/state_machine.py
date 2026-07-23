"""
Explicit 15-State Task State Machine for WindAgent Architecture V2.
Validates state transitions and prevents illegal task lifecycle movements.
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Dict, Set

from windagent_core.errors.exceptions import DomainError

logger = logging.getLogger("windagent.orchestration.state_machine")


class TaskState(str, Enum):
    RECEIVED = "received"
    CLASSIFYING = "classifying"
    CONTEXT_BUILDING = "context_building"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    RECOVERING = "recovering"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Explicit transition matrix mapping allowed from_state -> set(to_states)
ALLOWED_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.RECEIVED: {
        TaskState.CLASSIFYING, TaskState.CONTEXT_BUILDING, TaskState.PLANNING,
        TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.CLASSIFYING: {
        TaskState.CONTEXT_BUILDING, TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.CONTEXT_BUILDING: {
        TaskState.PLANNING, TaskState.READY, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.PLANNING: {
        TaskState.READY, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.READY: {
        TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.RUNNING: {
        TaskState.WAITING_PERMISSION, TaskState.PAUSED, TaskState.RETRY_WAIT,
        TaskState.VERIFYING, TaskState.REVIEWING, TaskState.COMPLETED,
        TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.WAITING_PERMISSION: {
        TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED
    },
    TaskState.PAUSED: {
        TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED
    },
    TaskState.RETRY_WAIT: {
        TaskState.RUNNING, TaskState.RECOVERING, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.RECOVERING: {
        TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.VERIFYING: {
        TaskState.REVIEWING, TaskState.COMPLETED, TaskState.RETRY_WAIT,
        TaskState.FAILED, TaskState.CANCELLED
    },
    TaskState.REVIEWING: {
        TaskState.COMPLETED, TaskState.RETRY_WAIT, TaskState.FAILED, TaskState.CANCELLED
    },
    # Terminal States - no outgoing transitions allowed
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


class TaskStateMachine:
    @staticmethod
    def is_terminal(state: TaskState) -> bool:
        return state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)

    @staticmethod
    def can_transition(current: TaskState, target: TaskState) -> bool:
        if current == target:
            return True
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        return target in allowed

    @staticmethod
    def transition(current: TaskState, target: TaskState) -> TaskState:
        if current == target:
            return current

        if not TaskStateMachine.can_transition(current, target):
            logger.error(f"Illegal state transition requested: [{current.value}] -> [{target.value}]")
            raise DomainError(
                message=f"Illegal state transition from [{current.value}] to [{target.value}].",
                code="WINDAGENT_ERR_ILLEGAL_STATE_TRANSITION",
                details={"current_state": current.value, "target_state": target.value},
            )

        logger.info(f"Task state transitioned: [{current.value}] -> [{target.value}]")
        return target
