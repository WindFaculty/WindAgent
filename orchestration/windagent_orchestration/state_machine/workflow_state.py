"""
WorkflowState Canonical Alias & StateMachine for WindAgent Orchestration (Phase 8 Adoption).
Re-exports canonical WorkflowState and delegates transitions to WorkflowLifecycle.
"""

from __future__ import annotations
from typing import Any
from windagent_core.domain.lifecycle import WorkflowState, WorkflowLifecycle

__all__ = ["WorkflowState", "WorkflowLifecycle", "WorkflowStateMachine"]


def parse_workflow_state(val: Any) -> WorkflowState:
    if isinstance(val, WorkflowState):
        return val
    raw = val.value if hasattr(val, "value") else str(val)
    raw_str = str(raw).upper()
    try:
        return WorkflowState[raw_str]
    except KeyError:
        return WorkflowState(raw_str.lower())


class WorkflowStateMachine:
    """Delegates workflow state transitions to canonical core WorkflowLifecycle."""

    @staticmethod
    def is_terminal(state: WorkflowState | str) -> bool:
        st = parse_workflow_state(state)
        return WorkflowLifecycle.is_terminal(st)

    @staticmethod
    def can_transition(current: WorkflowState | str, target: WorkflowState | str) -> bool:
        curr_st = parse_workflow_state(current)
        targ_st = parse_workflow_state(target)
        return WorkflowLifecycle.can_transition(curr_st, targ_st)

    @staticmethod
    def transition(current: WorkflowState | str, target: WorkflowState | str) -> WorkflowState:
        curr_st = parse_workflow_state(current)
        targ_st = parse_workflow_state(target)
        res = WorkflowLifecycle.transition(curr_st, targ_st)
        return parse_workflow_state(res.new_state)
