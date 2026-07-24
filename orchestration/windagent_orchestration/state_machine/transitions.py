"""
Task Transition Matrix & Validator for WindAgent Orchestration V2 (Phase 8 Adoption).
Delegates state transition enforcement to canonical windagent_core.domain.lifecycle.TaskLifecycle.
"""

from __future__ import annotations
import logging
from typing import Dict, Set, Any

from windagent_core.domain.lifecycle import TaskState, TaskLifecycle
from windagent_core.errors.exceptions import InvalidStateTransitionError, TerminalStateMutationError, DomainError

logger = logging.getLogger("windagent.orchestration.state_machine")

ALLOWED_TRANSITIONS: Dict[TaskState, Set[TaskState]] = TaskLifecycle.LEGAL_TRANSITIONS


def parse_task_state(val: Any) -> TaskState:
    if isinstance(val, TaskState):
        return val
    raw = val.value if hasattr(val, "value") else str(val)
    raw_str = str(raw).upper()
    try:
        return TaskState[raw_str]
    except KeyError:
        return TaskState(raw_str.lower())


class TaskStateMachine:
    """Delegates task lifecycle transitions to core TaskLifecycle."""

    @staticmethod
    def is_terminal(state: TaskState | str) -> bool:
        st = parse_task_state(state)
        return TaskLifecycle.is_terminal(st)

    @staticmethod
    def can_transition(current: TaskState | str, target: TaskState | str) -> bool:
        curr_st = parse_task_state(current)
        targ_st = parse_task_state(target)
        return TaskLifecycle.can_transition(curr_st, targ_st)

    @staticmethod
    def transition(current: TaskState | str, target: TaskState | str) -> TaskState:
        curr_st = parse_task_state(current)
        targ_st = parse_task_state(target)
        res = TaskLifecycle.transition(curr_st, targ_st)
        return parse_task_state(res.to_state)
