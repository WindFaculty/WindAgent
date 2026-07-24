"""
Canonical 15-State Lifecycle Engine & Optimistic Concurrency Control for WindAgent Core (Phase 3 & Phase 8).
Enforces exact legal transition matrices, immutable terminal states, and optimistic version checks.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Set, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.errors.exceptions import (
    InvalidStateTransitionError,
    TerminalStateMutationError,
    ConcurrentStateConflictError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskState(str, Enum):
    """Canonical 15-state lifecycle enumeration for Task / TaskRun aggregates."""
    RECEIVED = "RECEIVED"
    CLASSIFYING = "CLASSIFYING"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_PERMISSION = "WAITING_PERMISSION"
    PAUSED = "PAUSED"
    RETRY_WAIT = "RETRY_WAIT"
    RECOVERING = "RECOVERING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowState(str, Enum):
    """Canonical lifecycle enumeration for Workflow definitions and executions."""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepState(str, Enum):
    """Canonical lifecycle enumeration for WorkflowStep / StepRun executions."""
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING_PERMISSION = "WAITING_PERMISSION"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class SessionState(str, Enum):
    """Canonical lifecycle enumeration for user/chat Session aggregates."""
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class StateTransitionResult(BaseModel):
    """Result payload emitted after a successful aggregate state transition."""
    aggregate_id: str
    from_state: str
    to_state: str
    previous_version: int
    new_version: int
    occurred_at: datetime = Field(default_factory=utc_now)
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")


def parse_transition_kwargs(
    first: Any = None,
    second: Any = None,
    third: Any = None,
    fourth: Any = None,
    aggregate_id: Optional[str] = None,
    current: Any = None,
    target: Any = None,
    current_version: int = 0,
) -> tuple[str, Any, Any, int]:
    if aggregate_id is not None or current is not None or target is not None:
        agg = aggregate_id or "aggregate"
        curr = current if current is not None else first
        targ = target if target is not None else second
        ver = current_version
        return agg, curr, targ, ver

    if isinstance(first, str) and not isinstance(first, Enum):
        return first, second, third, int(fourth) if fourth is not None else 0
    else:
        return "aggregate", first, second, int(third) if third is not None else 0


class TaskLifecycle:
    """State transition machine and legal matrix enforcement for Task aggregates."""
    TERMINAL_STATES: Set[TaskState] = {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    }

    LEGAL_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
        TaskState.RECEIVED: {TaskState.CLASSIFYING, TaskState.CONTEXT_BUILDING, TaskState.PLANNING, TaskState.READY, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.CLASSIFYING: {TaskState.CONTEXT_BUILDING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.CONTEXT_BUILDING: {TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.PLANNING: {TaskState.READY, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.READY: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED},
        TaskState.RUNNING: {
            TaskState.WAITING_PERMISSION,
            TaskState.PAUSED,
            TaskState.RETRY_WAIT,
            TaskState.RECOVERING,
            TaskState.VERIFYING,
            TaskState.REVIEWING,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        },
        TaskState.WAITING_PERMISSION: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED},
        TaskState.PAUSED: {TaskState.RUNNING, TaskState.CANCELLED},
        TaskState.RETRY_WAIT: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
        TaskState.RECOVERING: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.VERIFYING: {TaskState.REVIEWING, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.REVIEWING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.COMPLETED: set(),
        TaskState.FAILED: set(),
        TaskState.CANCELLED: set(),
    }

    @classmethod
    def is_terminal(cls, state: TaskState) -> bool:
        return state in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: TaskState, target: TaskState) -> bool:
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        first: Any = None,
        second: Any = None,
        third: Any = None,
        fourth: Any = None,
        aggregate_id: Optional[str] = None,
        current: Any = None,
        target: Any = None,
        current_version: int = 0,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StateTransitionResult:
        agg_id, curr_raw, targ_raw, curr_ver = parse_transition_kwargs(
            first, second, third, fourth, aggregate_id, current, target, current_version
        )

        curr_val = curr_raw.value if hasattr(curr_raw, "value") else str(curr_raw)
        targ_val = targ_raw.value if hasattr(targ_raw, "value") else str(targ_raw)
        curr_st = TaskState[curr_val.upper()] if isinstance(curr_raw, str) else curr_raw
        targ_st = TaskState[targ_val.upper()] if isinstance(targ_raw, str) else targ_raw

        if expected_version is not None and expected_version != curr_ver:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for Task {agg_id}: expected version {expected_version}, actual version {curr_ver}"
            )
        if cls.is_terminal(curr_st):
            raise TerminalStateMutationError(
                f"Cannot transition terminal Task state {curr_val} to {targ_val}"
            )
        legal_targets = cls.LEGAL_TRANSITIONS.get(curr_st, set())
        if targ_st not in legal_targets:
            raise InvalidStateTransitionError(
                f"Illegal state transition from {curr_val} to {targ_val}. Allowed: {[s.value for s in legal_targets]}"
            )
        return StateTransitionResult(
            aggregate_id=agg_id,
            from_state=curr_val,
            to_state=targ_val,
            previous_version=curr_ver,
            new_version=curr_ver + 1,
            reason=reason,
        )


class WorkflowLifecycle:
    """State transition machine and legal matrix enforcement for Workflow aggregates."""
    TERMINAL_STATES: Set[WorkflowState] = {
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    }

    LEGAL_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
        WorkflowState.DRAFT: {WorkflowState.READY, WorkflowState.CANCELLED},
        WorkflowState.PENDING: {WorkflowState.READY, WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.READY: {WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.CANCELLED},
        WorkflowState.RUNNING: {WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.PAUSED: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
        WorkflowState.COMPLETED: set(),
        WorkflowState.FAILED: set(),
        WorkflowState.CANCELLED: set(),
    }

    @classmethod
    def is_terminal(cls, state: WorkflowState) -> bool:
        return state in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: WorkflowState, target: WorkflowState) -> bool:
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        first: Any = None,
        second: Any = None,
        third: Any = None,
        fourth: Any = None,
        aggregate_id: Optional[str] = None,
        current: Any = None,
        target: Any = None,
        current_version: int = 0,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StateTransitionResult:
        agg_id, curr_raw, targ_raw, curr_ver = parse_transition_kwargs(
            first, second, third, fourth, aggregate_id, current, target, current_version
        )

        curr_val = curr_raw.value if hasattr(curr_raw, "value") else str(curr_raw)
        targ_val = targ_raw.value if hasattr(targ_raw, "value") else str(targ_raw)
        curr_st = WorkflowState[curr_val.upper()] if isinstance(curr_raw, str) else curr_raw
        targ_st = WorkflowState[targ_val.upper()] if isinstance(targ_raw, str) else targ_raw

        if expected_version is not None and expected_version != curr_ver:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for Workflow {agg_id}: expected version {expected_version}, actual version {curr_ver}"
            )
        if cls.is_terminal(curr_st):
            raise TerminalStateMutationError(
                f"Cannot transition terminal Workflow state {curr_val} to {targ_val}"
            )
        legal_targets = cls.LEGAL_TRANSITIONS.get(curr_st, set())
        if targ_st not in legal_targets:
            raise InvalidStateTransitionError(
                f"Illegal Workflow transition from {curr_val} to {targ_val}. Allowed: {[s.value for s in legal_targets]}"
            )
        return StateTransitionResult(
            aggregate_id=agg_id,
            from_state=curr_val,
            to_state=targ_val,
            previous_version=curr_ver,
            new_version=curr_ver + 1,
            reason=reason,
        )


class StepLifecycle:
    """State transition machine and legal matrix enforcement for Step runs."""
    TERMINAL_STATES: Set[StepState] = {
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.SKIPPED,
        StepState.CANCELLED,
    }

    LEGAL_TRANSITIONS: Dict[StepState, Set[StepState]] = {
        StepState.BLOCKED: {StepState.READY, StepState.SKIPPED, StepState.CANCELLED},
        StepState.PENDING: {StepState.READY, StepState.CLAIMED, StepState.DISPATCHED, StepState.RUNNING, StepState.SKIPPED, StepState.CANCELLED, StepState.FAILED},
        StepState.READY: {StepState.CLAIMED, StepState.DISPATCHED, StepState.SKIPPED, StepState.CANCELLED},
        StepState.CLAIMED: {StepState.DISPATCHED, StepState.CANCELLED, StepState.FAILED},
        StepState.DISPATCHED: {StepState.RUNNING, StepState.RETRY_WAIT, StepState.FAILED, StepState.CANCELLED},
        StepState.RUNNING: {
            StepState.WAITING_PERMISSION,
            StepState.RETRY_WAIT,
            StepState.COMPLETED,
            StepState.FAILED,
            StepState.CANCELLED,
        },
        StepState.WAITING_PERMISSION: {StepState.RUNNING, StepState.FAILED, StepState.CANCELLED},
        StepState.RETRY_WAIT: {StepState.READY, StepState.RUNNING, StepState.FAILED, StepState.CANCELLED},
        StepState.COMPLETED: set(),
        StepState.FAILED: set(),
        StepState.SKIPPED: set(),
        StepState.CANCELLED: set(),
    }

    @classmethod
    def is_terminal(cls, state: StepState) -> bool:
        return state in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: StepState, target: StepState) -> bool:
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        first: Any = None,
        second: Any = None,
        third: Any = None,
        fourth: Any = None,
        aggregate_id: Optional[str] = None,
        current: Any = None,
        target: Any = None,
        current_version: int = 0,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StateTransitionResult:
        agg_id, curr_raw, targ_raw, curr_ver = parse_transition_kwargs(
            first, second, third, fourth, aggregate_id, current, target, current_version
        )

        curr_val = curr_raw.value if hasattr(curr_raw, "value") else str(curr_raw)
        targ_val = targ_raw.value if hasattr(targ_raw, "value") else str(targ_raw)
        curr_st = StepState[curr_val.upper()] if isinstance(curr_raw, str) else curr_raw
        targ_st = StepState[targ_val.upper()] if isinstance(targ_raw, str) else targ_raw

        if expected_version is not None and expected_version != curr_ver:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for Step {agg_id}: expected version {expected_version}, actual version {curr_ver}"
            )
        if cls.is_terminal(curr_st):
            raise TerminalStateMutationError(
                f"Cannot transition terminal Step state {curr_val} to {targ_val}"
            )
        legal_targets = cls.LEGAL_TRANSITIONS.get(curr_st, set())
        if targ_st not in legal_targets:
            raise InvalidStateTransitionError(
                f"Illegal Step transition from {curr_val} to {targ_val}. Allowed: {[s.value for s in legal_targets]}"
            )
        return StateTransitionResult(
            aggregate_id=agg_id,
            from_state=curr_val,
            to_state=targ_val,
            previous_version=curr_ver,
            new_version=curr_ver + 1,
            reason=reason,
        )


class SessionLifecycle:
    """State transition machine and legal matrix enforcement for Session aggregates."""
    TERMINAL_STATES: Set[SessionState] = {
        SessionState.ARCHIVED,
    }

    LEGAL_TRANSITIONS: Dict[SessionState, Set[SessionState]] = {
        SessionState.IDLE: {SessionState.ACTIVE, SessionState.ARCHIVED, SessionState.CANCELLED},
        SessionState.ACTIVE: {SessionState.IDLE, SessionState.PAUSED, SessionState.COMPLETED, SessionState.FAILED, SessionState.CANCELLED, SessionState.ARCHIVED},
        SessionState.PAUSED: {SessionState.ACTIVE, SessionState.CANCELLED, SessionState.ARCHIVED},
        SessionState.COMPLETED: {SessionState.ARCHIVED},
        SessionState.FAILED: {SessionState.ARCHIVED},
        SessionState.CANCELLED: {SessionState.ARCHIVED},
        SessionState.ARCHIVED: set(),
    }

    @classmethod
    def is_terminal(cls, state: SessionState) -> bool:
        return state in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: SessionState, target: SessionState) -> bool:
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        first: Any = None,
        second: Any = None,
        third: Any = None,
        fourth: Any = None,
        aggregate_id: Optional[str] = None,
        current: Any = None,
        target: Any = None,
        current_version: int = 0,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StateTransitionResult:
        agg_id, curr_raw, targ_raw, curr_ver = parse_transition_kwargs(
            first, second, third, fourth, aggregate_id, current, target, current_version
        )

        curr_val = curr_raw.value if hasattr(curr_raw, "value") else str(curr_raw)
        targ_val = targ_raw.value if hasattr(targ_raw, "value") else str(targ_raw)
        curr_st = SessionState[curr_val.upper()] if isinstance(curr_raw, str) else curr_raw
        targ_st = SessionState[targ_val.upper()] if isinstance(targ_raw, str) else targ_raw

        if expected_version is not None and expected_version != curr_ver:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for Session {agg_id}: expected version {expected_version}, actual version {curr_ver}"
            )
        if cls.is_terminal(curr_st):
            raise TerminalStateMutationError(
                f"Cannot transition terminal Session state {curr_val} to {targ_val}"
            )
        legal_targets = cls.LEGAL_TRANSITIONS.get(curr_st, set())
        if targ_st not in legal_targets:
            raise InvalidStateTransitionError(
                f"Illegal Session transition from {curr_val} to {targ_val}. Allowed: {[s.value for s in legal_targets]}"
            )
        return StateTransitionResult(
            aggregate_id=agg_id,
            from_state=curr_val,
            to_state=targ_val,
            previous_version=curr_ver,
            new_version=curr_ver + 1,
            reason=reason,
        )
