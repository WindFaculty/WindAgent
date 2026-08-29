"""Persistent Goal domain for long-running hardened agents (Phase 5).

Implements a durable goal authority that lives independently of volatile
worker/UI/API lifetimes. All transitions are version-guarded (CAS) in
storage; this layer defines legal states, immutability helpers, and
the fail-closed rules required by ban_ke_hoach_v1 §10.

Goal is NOT a plan node — it tracks the long-running objective whose
progress is checkpointed at turn/tool/child/compaction/wait/terminal
boundaries. One Conversation / ParentTask may own one or more Goals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.errors.exceptions import (
    ConcurrentStateConflictError,
    InvalidStateTransitionError,
    TerminalStateMutationError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_GOAL_STATES: Set[GoalStatus] = {
    GoalStatus.COMPLETED,
    GoalStatus.FAILED,
    GoalStatus.CANCELLED,
}

LEGAL_GOAL_TRANSITIONS: Dict[GoalStatus, Set[GoalStatus]] = {
    GoalStatus.ACTIVE: {
        GoalStatus.IN_PROGRESS,
        GoalStatus.BLOCKED,
        GoalStatus.PAUSED,
        GoalStatus.COMPLETED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    },
    GoalStatus.IN_PROGRESS: {
        GoalStatus.BLOCKED,
        GoalStatus.PAUSED,
        GoalStatus.COMPLETED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    },
    GoalStatus.BLOCKED: {
        GoalStatus.IN_PROGRESS,
        GoalStatus.PAUSED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    },
    GoalStatus.PAUSED: {
        GoalStatus.ACTIVE,
        GoalStatus.IN_PROGRESS,
        GoalStatus.BLOCKED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    },
    GoalStatus.COMPLETED: set(),
    GoalStatus.FAILED: set(),
    GoalStatus.CANCELLED: set(),
}


class GoalTransitionResult(BaseModel):
    aggregate_id: str
    from_status: str
    to_status: str
    previous_version: int
    new_version: int
    occurred_at: datetime = Field(default_factory=utc_now)
    reason: Optional[str] = None

    model_config = ConfigDict(frozen=True, extra="forbid")


class PersistentGoal(BaseModel):
    """Immutable snapshot of a durable goal (Phase 5 §10).

    Fields per roadmap:
      goal_id, objective, status, progress_summary, started_at,
      last_progress_at, completion_criteria, blocked_reason
    plus version/CAS and optional ownership edges.
    """

    goal_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    status: GoalStatus = Field(default=GoalStatus.ACTIVE)
    progress_summary: str = Field(default="")
    started_at: datetime = Field(default_factory=utc_now)
    last_progress_at: Optional[datetime] = Field(default=None)
    completion_criteria: Dict[str, Any] = Field(default_factory=dict)
    blocked_reason: Optional[str] = Field(default=None)
    # ownership edges — all optional, but at least one of conversation/parent matters
    conversation_id: Optional[str] = Field(default=None)
    parent_task_id: Optional[str] = Field(default=None)
    agent_run_id: Optional[str] = Field(default=None)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    # harness/version context — stored for trajectory correlation
    harness_version: Optional[str] = Field(default=None)

    model_config = ConfigDict(frozen=True, extra="forbid")


class GoalLifecycle:
    TERMINAL_STATES = TERMINAL_GOAL_STATES
    LEGAL_TRANSITIONS = LEGAL_GOAL_TRANSITIONS

    @classmethod
    def is_terminal(cls, status: GoalStatus | str) -> bool:
        if isinstance(status, str):
            try:
                status = GoalStatus(status)
            except ValueError:
                return False
        return status in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: GoalStatus | str, target: GoalStatus | str) -> bool:
        if isinstance(current, str):
            current = GoalStatus(current)
        if isinstance(target, str):
            target = GoalStatus(target)
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: GoalStatus, target: GoalStatus) -> None:
        if cls.is_terminal(current):
            raise TerminalStateMutationError(
                f"Cannot transition terminal goal {current.value} -> {target.value}"
            )
        if not cls.can_transition(current, target):
            allowed = sorted(s.value for s in cls.LEGAL_TRANSITIONS.get(current, set()))
            raise InvalidStateTransitionError(
                f"Illegal goal transition {current.value} -> {target.value}. Allowed: {allowed}"
            )

    @classmethod
    def transition(
        cls,
        *,
        aggregate_id: str,
        current: GoalStatus | str,
        target: GoalStatus | str,
        current_version: int,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> GoalTransitionResult:
        cur = current if isinstance(current, GoalStatus) else GoalStatus(str(current).upper())
        tgt = target if isinstance(target, GoalStatus) else GoalStatus(str(target).upper())
        if expected_version is not None and expected_version != current_version:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for Goal {aggregate_id}: expected {expected_version}, actual {current_version}"
            )
        if cur == tgt:
            return GoalTransitionResult(
                aggregate_id=aggregate_id,
                from_status=cur.value,
                to_status=tgt.value,
                previous_version=current_version,
                new_version=current_version,
                reason=reason,
            )
        cls.validate_transition(cur, tgt)
        return GoalTransitionResult(
            aggregate_id=aggregate_id,
            from_status=cur.value,
            to_status=tgt.value,
            previous_version=current_version,
            new_version=current_version + 1,
            reason=reason,
        )


__all__ = [
    "GoalStatus",
    "PersistentGoal",
    "GoalLifecycle",
    "GoalTransitionResult",
    "LEGAL_GOAL_TRANSITIONS",
    "TERMINAL_GOAL_STATES",
]
