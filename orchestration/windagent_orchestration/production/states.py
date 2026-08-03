"""
Production run state machine for WindAgent Durable Production Workflow (plan 05 §8.1).

Defines the 11 canonical run states required by plan 05:

    CREATED, RUNNING, WAITING_APPROVAL, WAITING_HUMAN_ACTION,
    WAITING_PROVIDER, PAUSED, RECOVERING, COMPLETED, FAILED,
    CANCELLED, ARCHIVED

Transitions use the canonical command/event discipline:

- duplicate events are idempotent (a same-state "transition" is a no-op that
  still records the event once);
- terminal states (COMPLETED / FAILED / CANCELLED) accept no new writes other
  than audit/archival (ARCHIVED);
- stale worker writes are rejected by the lease/version check performed by the
  engine (see engine.py) — the state machine itself is pure and deterministic.

The state machine intentionally reuses the fail-closed conventions of
``windagent_core.domain.lifecycle`` (terminal sets, legal matrices, explicit
illegal-transition errors) without redefining the canonical core enums.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Set

from windagent_core.errors.exceptions import (
    InvalidStateTransitionError,
    TerminalStateMutationError,
)


class ProductionRunState(str, Enum):
    """Canonical lifecycle of a durable video-production workflow run."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_HUMAN_ACTION = "WAITING_HUMAN_ACTION"
    WAITING_PROVIDER = "WAITING_PROVIDER"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class ProductionStepState(str, Enum):
    """Lifecycle of a single step attempt inside a durable run (plan 05 §7)."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_HUMAN_ACTION = "WAITING_HUMAN_ACTION"
    WAITING_PROVIDER = "WAITING_PROVIDER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


def parse_run_state(val: Any) -> ProductionRunState:
    """Normalize a str/enum value into a ProductionRunState (fail closed)."""
    if isinstance(val, ProductionRunState):
        return val
    raw = val.value if hasattr(val, "value") else str(val)
    raw_str = str(raw).upper()
    try:
        return ProductionRunState[raw_str]
    except KeyError:
        return ProductionRunState(raw_str)


class ProductionRunStateMachine:
    """Deterministic transition matrix for ProductionRunState (plan 05 §8.1)."""

    TERMINAL_STATES: Set[ProductionRunState] = {
        ProductionRunState.COMPLETED,
        ProductionRunState.FAILED,
        ProductionRunState.CANCELLED,
    }

    # ARCHIVED is the only non-terminal sink; it is terminal in practice for
    # any new write except audit/archival, and the engine enforces that.
    LEGAL_TRANSITIONS: Dict[ProductionRunState, Set[ProductionRunState]] = {
        ProductionRunState.CREATED: {
            ProductionRunState.RUNNING,
            ProductionRunState.FAILED,
            ProductionRunState.CANCELLED,
            ProductionRunState.ARCHIVED,
        },
        ProductionRunState.RUNNING: {
            ProductionRunState.WAITING_APPROVAL,
            ProductionRunState.WAITING_HUMAN_ACTION,
            ProductionRunState.WAITING_PROVIDER,
            ProductionRunState.PAUSED,
            ProductionRunState.RECOVERING,
            ProductionRunState.COMPLETED,
            ProductionRunState.FAILED,
            ProductionRunState.CANCELLED,
        },
        ProductionRunState.WAITING_APPROVAL: {
            ProductionRunState.RUNNING,
            ProductionRunState.PAUSED,
            ProductionRunState.CANCELLED,
            ProductionRunState.FAILED,
        },
        ProductionRunState.WAITING_HUMAN_ACTION: {
            ProductionRunState.RUNNING,
            ProductionRunState.PAUSED,
            ProductionRunState.CANCELLED,
            ProductionRunState.FAILED,
        },
        ProductionRunState.WAITING_PROVIDER: {
            ProductionRunState.RUNNING,
            ProductionRunState.RECOVERING,
            ProductionRunState.PAUSED,
            ProductionRunState.CANCELLED,
            ProductionRunState.FAILED,
        },
        ProductionRunState.PAUSED: {
            ProductionRunState.RUNNING,
            ProductionRunState.CANCELLED,
            ProductionRunState.FAILED,
            ProductionRunState.ARCHIVED,
        },
        ProductionRunState.RECOVERING: {
            ProductionRunState.RUNNING,
            ProductionRunState.FAILED,
            ProductionRunState.CANCELLED,
        },
        ProductionRunState.COMPLETED: {
            ProductionRunState.ARCHIVED,
        },
        ProductionRunState.FAILED: {
            ProductionRunState.ARCHIVED,
        },
        ProductionRunState.CANCELLED: {
            ProductionRunState.ARCHIVED,
        },
        ProductionRunState.ARCHIVED: set(),
    }

    @classmethod
    def is_terminal(cls, state: ProductionRunState | str) -> bool:
        st = parse_run_state(state)
        return st in cls.TERMINAL_STATES

    @classmethod
    def is_sink(cls, state: ProductionRunState | str) -> bool:
        """ARCHIVED is a sink — no further non-audit writes are allowed."""
        return parse_run_state(state) == ProductionRunState.ARCHIVED

    @classmethod
    def can_transition(cls, current: ProductionRunState | str, target: ProductionRunState | str) -> bool:
        curr = parse_run_state(current)
        targ = parse_run_state(target)
        if curr == targ:
            return True  # idempotent no-op
        return targ in cls.LEGAL_TRANSITIONS.get(curr, set())

    @classmethod
    def transition(
        cls,
        current: ProductionRunState | str,
        target: ProductionRunState | str,
        *,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and apply a run state transition.

        Returns an audit-friendly transition record. Raises on illegal or
        terminal-source transitions (fail closed). Idempotent same-state
        transitions return a record with ``changed=False``.
        """
        curr = parse_run_state(current)
        targ = parse_run_state(target)

        if curr == targ:
            return {
                "from_state": curr.value,
                "to_state": targ.value,
                "changed": False,
                "reason": reason,
            }

        if cls.is_terminal(curr):
            raise TerminalStateMutationError(
                f"Cannot transition terminal ProductionRunState {curr.value} -> {targ.value}",
                details={"from": curr.value, "to": targ.value},
            )
        if cls.is_sink(curr):
            raise TerminalStateMutationError(
                f"Cannot write to archived ProductionRunState {curr.value} -> {targ.value}",
                details={"from": curr.value, "to": targ.value},
            )

        legal = cls.LEGAL_TRANSITIONS.get(curr, set())
        if targ not in legal:
            raise InvalidStateTransitionError(
                f"Illegal ProductionRunState transition {curr.value} -> {targ.value}. "
                f"Allowed: {sorted(s.value for s in legal)}",
                details={"from": curr.value, "to": targ.value, "allowed": sorted(s.value for s in legal)},
            )

        return {
            "from_state": curr.value,
            "to_state": targ.value,
            "changed": True,
            "reason": reason,
        }

    @classmethod
    def all_states(cls) -> list[str]:
        return [s.value for s in ProductionRunState]


class ProductionStepStateMachine:
    """Deterministic transition matrix for ProductionStepState (plan 05 §7)."""

    TERMINAL_STATES: Set[ProductionStepState] = {
        ProductionStepState.COMPLETED,
        ProductionStepState.FAILED,
        ProductionStepState.SKIPPED,
        ProductionStepState.CANCELLED,
    }

    LEGAL_TRANSITIONS: Dict[ProductionStepState, Set[ProductionStepState]] = {
        ProductionStepState.PENDING: {
            ProductionStepState.READY,
            ProductionStepState.SKIPPED,
            ProductionStepState.CANCELLED,
        },
        ProductionStepState.READY: {
            ProductionStepState.RUNNING,
            ProductionStepState.SKIPPED,
            ProductionStepState.CANCELLED,
        },
        ProductionStepState.RUNNING: {
            ProductionStepState.WAITING_APPROVAL,
            ProductionStepState.WAITING_HUMAN_ACTION,
            ProductionStepState.WAITING_PROVIDER,
            ProductionStepState.COMPLETED,
            ProductionStepState.FAILED,
            ProductionStepState.CANCELLED,
        },
        ProductionStepState.WAITING_APPROVAL: {
            ProductionStepState.RUNNING,
            ProductionStepState.CANCELLED,
            ProductionStepState.FAILED,
        },
        ProductionStepState.WAITING_HUMAN_ACTION: {
            ProductionStepState.RUNNING,
            ProductionStepState.CANCELLED,
            ProductionStepState.FAILED,
        },
        ProductionStepState.WAITING_PROVIDER: {
            ProductionStepState.RUNNING,
            ProductionStepState.COMPLETED,
            ProductionStepState.FAILED,
            ProductionStepState.CANCELLED,
        },
        ProductionStepState.COMPLETED: set(),
        ProductionStepState.FAILED: set(),
        ProductionStepState.SKIPPED: set(),
        ProductionStepState.CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, current: ProductionStepState, target: ProductionStepState) -> bool:
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def transition(cls, current: ProductionStepState, target: ProductionStepState) -> ProductionStepState:
        if not cls.can_transition(current, target):
            raise InvalidStateTransitionError(
                f"Illegal ProductionStepState transition {current.value} -> {target.value}",
                details={"from": current.value, "to": target.value},
            )
        return target


__all__ = [
    "ProductionRunState",
    "ProductionStepState",
    "parse_run_state",
    "ProductionRunStateMachine",
    "ProductionStepStateMachine",
]
