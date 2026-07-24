"""
StepState Canonical Alias & StateMachine for WindAgent Orchestration (Phase 8 Adoption).
Re-exports canonical StepState and delegates transitions to StepLifecycle.
"""

from __future__ import annotations
from typing import Any
from windagent_core.domain.lifecycle import StepState, StepLifecycle

__all__ = ["StepState", "StepLifecycle", "StepStateMachine"]


def parse_step_state(val: Any) -> StepState:
    if isinstance(val, StepState):
        return val
    raw = val.value if hasattr(val, "value") else str(val)
    raw_str = str(raw).upper()
    try:
        return StepState[raw_str]
    except KeyError:
        return StepState(raw_str.lower())


class StepStateMachine:
    """Delegates step state transitions to canonical core StepLifecycle."""

    @staticmethod
    def is_terminal(state: StepState | str) -> bool:
        st = parse_step_state(state)
        return StepLifecycle.is_terminal(st)

    @staticmethod
    def can_transition(current: StepState | str, target: StepState | str) -> bool:
        curr_st = parse_step_state(current)
        targ_st = parse_step_state(target)
        return StepLifecycle.can_transition(curr_st, targ_st)

    @staticmethod
    def transition(current: StepState | str, target: StepState | str) -> StepState:
        curr_st = parse_step_state(current)
        targ_st = parse_step_state(target)
        res = StepLifecycle.transition(curr_st, targ_st)
        return parse_step_state(res.new_state)
