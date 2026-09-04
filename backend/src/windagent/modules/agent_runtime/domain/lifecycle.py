"""Canonical lifecycles for Agent Runtime (Phase 13).

REWRITTEN from ``windagent_core.domain.lifecycle`` and
``windagent_core.domain.agent_loop`` but owned by V2.  No legacy imports.

Covers:
- ``SessionState``  — user/agent session (7 states)
- ``AgentLoopState`` — durable agent-run loop (12 states) + budget-aware
- ``TaskState``     — 15-state task lifecycle
- ``WorkflowState`` — 8-state workflow lifecycle
- ``StepState``     — 12-state workflow step lifecycle

Each class is a pure StrEnum + frozen transition table; ``transition`` helpers
raise the module error taxonomy, not the old core exceptions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --------------------------------------------------------------------------- #
# Session (mirrors core SessionState)
# --------------------------------------------------------------------------- #


class SessionState(StrEnum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


SESSION_TERMINAL: Final[frozenset[SessionState]] = frozenset(
    {SessionState.COMPLETED, SessionState.FAILED, SessionState.CANCELLED, SessionState.ARCHIVED}
)


class SessionLifecycle:
    TRANSITIONS: Final[dict[SessionState, frozenset[SessionState]]] = {
        SessionState.IDLE: frozenset({SessionState.ACTIVE, SessionState.CANCELLED, SessionState.ARCHIVED}),
        SessionState.ACTIVE: frozenset(
            {SessionState.PAUSED, SessionState.COMPLETED, SessionState.FAILED, SessionState.CANCELLED, SessionState.ARCHIVED}
        ),
        SessionState.PAUSED: frozenset({SessionState.ACTIVE, SessionState.FAILED, SessionState.CANCELLED, SessionState.ARCHIVED}),
        SessionState.COMPLETED: frozenset({SessionState.ARCHIVED}),
        SessionState.FAILED: frozenset({SessionState.IDLE, SessionState.ARCHIVED}),
        SessionState.CANCELLED: frozenset({SessionState.IDLE, SessionState.ARCHIVED}),
        SessionState.ARCHIVED: frozenset(),
    }

    @classmethod
    def is_terminal(cls, state: SessionState) -> bool:
        return state in SESSION_TERMINAL

    @classmethod
    def can_transition(cls, current: SessionState, target: SessionState) -> bool:
        if current == target:
            return True
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: SessionState, target: SessionState) -> SessionState:
        if not cls.can_transition(current, target):
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Illegal session transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        return target


# --------------------------------------------------------------------------- #
# Agent loop (durable 12-state)
# --------------------------------------------------------------------------- #


class AgentLoopState(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_CHILD = "WAITING_CHILD"
    WAITING_SCHEDULE = "WAITING_SCHEDULE"
    COMPACTING = "COMPACTING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ORPHANED = "ORPHANED"


AGENT_LOOP_TERMINAL: Final[frozenset[AgentLoopState]] = frozenset(
    {AgentLoopState.COMPLETED, AgentLoopState.FAILED, AgentLoopState.CANCELLED, AgentLoopState.ORPHANED}
)


class AgentLoopLifecycle:
    TRANSITIONS: Final[dict[AgentLoopState, frozenset[AgentLoopState]]] = {
        AgentLoopState.CREATED: frozenset({AgentLoopState.READY, AgentLoopState.FAILED, AgentLoopState.CANCELLED}),
        AgentLoopState.READY: frozenset({AgentLoopState.RUNNING, AgentLoopState.FAILED, AgentLoopState.CANCELLED}),
        AgentLoopState.RUNNING: frozenset(
            {
                AgentLoopState.WAITING_TOOL,
                AgentLoopState.WAITING_CHILD,
                AgentLoopState.WAITING_SCHEDULE,
                AgentLoopState.COMPACTING,
                AgentLoopState.PAUSED,
                AgentLoopState.COMPLETED,
                AgentLoopState.FAILED,
                AgentLoopState.CANCELLED,
                AgentLoopState.ORPHANED,
            }
        ),
        AgentLoopState.WAITING_TOOL: frozenset(
            {
                AgentLoopState.RUNNING,
                AgentLoopState.PAUSED,
                AgentLoopState.COMPACTING,
                AgentLoopState.COMPLETED,
                AgentLoopState.FAILED,
                AgentLoopState.CANCELLED,
                AgentLoopState.ORPHANED,
            }
        ),
        AgentLoopState.WAITING_CHILD: frozenset(
            {
                AgentLoopState.RUNNING,
                AgentLoopState.PAUSED,
                AgentLoopState.COMPACTING,
                AgentLoopState.COMPLETED,
                AgentLoopState.FAILED,
                AgentLoopState.CANCELLED,
                AgentLoopState.ORPHANED,
            }
        ),
        AgentLoopState.WAITING_SCHEDULE: frozenset(
            {
                AgentLoopState.RUNNING,
                AgentLoopState.PAUSED,
                AgentLoopState.COMPACTING,
                AgentLoopState.COMPLETED,
                AgentLoopState.FAILED,
                AgentLoopState.CANCELLED,
                AgentLoopState.ORPHANED,
            }
        ),
        AgentLoopState.COMPACTING: frozenset(
            {AgentLoopState.RUNNING, AgentLoopState.PAUSED, AgentLoopState.FAILED, AgentLoopState.CANCELLED, AgentLoopState.ORPHANED}
        ),
        AgentLoopState.PAUSED: frozenset(
            {AgentLoopState.RUNNING, AgentLoopState.FAILED, AgentLoopState.CANCELLED, AgentLoopState.ORPHANED}
        ),
        AgentLoopState.COMPLETED: frozenset(),
        AgentLoopState.FAILED: frozenset(),
        AgentLoopState.CANCELLED: frozenset(),
        AgentLoopState.ORPHANED: frozenset(),
    }

    @classmethod
    def is_terminal(cls, state: AgentLoopState) -> bool:
        return state in AGENT_LOOP_TERMINAL

    @classmethod
    def can_transition(cls, current: AgentLoopState, target: AgentLoopState) -> bool:
        if current == target:
            return True
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: AgentLoopState, target: AgentLoopState) -> AgentLoopState:
        if current != target and not cls.can_transition(current, target):
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Illegal loop transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        if cls.is_terminal(current) and current != target:
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Cannot transition terminal loop state {current.value} to {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        return target


# --------------------------------------------------------------------------- #
# Task (15-state)
# --------------------------------------------------------------------------- #


class TaskState(StrEnum):
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


TASK_TERMINAL: Final[frozenset[TaskState]] = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED})


class TaskLifecycle:
    TRANSITIONS: Final[dict[TaskState, frozenset[TaskState]]] = {
        TaskState.RECEIVED: frozenset(
            {TaskState.CLASSIFYING, TaskState.CONTEXT_BUILDING, TaskState.PLANNING, TaskState.READY, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED}
        ),
        TaskState.CLASSIFYING: frozenset({TaskState.CONTEXT_BUILDING, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.CONTEXT_BUILDING: frozenset({TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.PLANNING: frozenset({TaskState.READY, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.READY: frozenset({TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED}),
        TaskState.RUNNING: frozenset(
            {
                TaskState.WAITING_PERMISSION,
                TaskState.PAUSED,
                TaskState.RETRY_WAIT,
                TaskState.RECOVERING,
                TaskState.VERIFYING,
                TaskState.REVIEWING,
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
            }
        ),
        TaskState.WAITING_PERMISSION: frozenset({TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED}),
        TaskState.PAUSED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
        TaskState.RETRY_WAIT: frozenset({TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED}),
        TaskState.RECOVERING: frozenset({TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.VERIFYING: frozenset({TaskState.REVIEWING, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.REVIEWING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.COMPLETED: frozenset(),
        TaskState.FAILED: frozenset({TaskState.RETRY_WAIT}),
        TaskState.CANCELLED: frozenset(),
    }

    @classmethod
    def is_terminal(cls, state: TaskState) -> bool:
        return state in TASK_TERMINAL

    @classmethod
    def can_transition(cls, current: TaskState, target: TaskState) -> bool:
        if current == target:
            return True
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: TaskState, target: TaskState) -> TaskState:
        if not cls.can_transition(current, target):
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Illegal task transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        if cls.is_terminal(current) and current != target:
            # Retry is the only allowed escape from FAILED (plan section 19)
            if not (current == TaskState.FAILED and target == TaskState.RETRY_WAIT):
                from .errors import AgentRuntimeInvalidTransitionError

                raise AgentRuntimeInvalidTransitionError(
                    f"Cannot transition terminal task state {current.value} to {target.value}.",
                    context={"current_state": current.value, "target_state": target.value},
                )
        return target


# --------------------------------------------------------------------------- #
# Workflow (8-state) + Step (12-state)
# --------------------------------------------------------------------------- #


class WorkflowState(StrEnum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


WORKFLOW_TERMINAL: Final[frozenset[WorkflowState]] = frozenset(
    {WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED}
)


class WorkflowLifecycle:
    TRANSITIONS: Final[dict[WorkflowState, frozenset[WorkflowState]]] = {
        WorkflowState.DRAFT: frozenset({WorkflowState.READY, WorkflowState.CANCELLED}),
        WorkflowState.PENDING: frozenset(
            {WorkflowState.READY, WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.FAILED, WorkflowState.CANCELLED}
        ),
        WorkflowState.READY: frozenset({WorkflowState.RUNNING, WorkflowState.PAUSED, WorkflowState.CANCELLED}),
        WorkflowState.RUNNING: frozenset({WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED}),
        WorkflowState.PAUSED: frozenset({WorkflowState.RUNNING, WorkflowState.CANCELLED}),
        WorkflowState.COMPLETED: frozenset(),
        WorkflowState.FAILED: frozenset(),
        WorkflowState.CANCELLED: frozenset(),
    }

    @classmethod
    def is_terminal(cls, state: WorkflowState) -> bool:
        return state in WORKFLOW_TERMINAL

    @classmethod
    def can_transition(cls, current: WorkflowState, target: WorkflowState) -> bool:
        if current == target:
            return True
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: WorkflowState, target: WorkflowState) -> WorkflowState:
        if not cls.can_transition(current, target):
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Illegal workflow transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        if cls.is_terminal(current) and current != target:
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Cannot transition terminal workflow state {current.value} to {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        return target


class StepState(StrEnum):
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


STEP_TERMINAL: Final[frozenset[StepState]] = frozenset(
    {StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED, StepState.CANCELLED}
)


class StepLifecycle:
    TRANSITIONS: Final[dict[StepState, frozenset[StepState]]] = {
        StepState.BLOCKED: frozenset({StepState.PENDING, StepState.SKIPPED, StepState.CANCELLED}),
        StepState.PENDING: frozenset({StepState.READY, StepState.BLOCKED, StepState.CANCELLED}),
        StepState.READY: frozenset({StepState.CLAIMED, StepState.CANCELLED}),
        StepState.CLAIMED: frozenset({StepState.DISPATCHED, StepState.CANCELLED}),
        StepState.DISPATCHED: frozenset({StepState.RUNNING, StepState.CANCELLED}),
        StepState.RUNNING: frozenset(
            {
                StepState.WAITING_PERMISSION,
                StepState.RETRY_WAIT,
                StepState.COMPLETED,
                StepState.FAILED,
                StepState.CANCELLED,
            }
        ),
        StepState.WAITING_PERMISSION: frozenset({StepState.RUNNING, StepState.CANCELLED, StepState.FAILED}),
        StepState.RETRY_WAIT: frozenset({StepState.RUNNING, StepState.FAILED, StepState.CANCELLED}),
        StepState.COMPLETED: frozenset(),
        StepState.FAILED: frozenset({StepState.RETRY_WAIT}),
        StepState.SKIPPED: frozenset(),
        StepState.CANCELLED: frozenset(),
    }

    @classmethod
    def is_terminal(cls, state: StepState) -> bool:
        return state in STEP_TERMINAL

    @classmethod
    def can_transition(cls, current: StepState, target: StepState) -> bool:
        if current == target:
            return True
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: StepState, target: StepState) -> StepState:
        if not cls.can_transition(current, target):
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Illegal step transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        if cls.is_terminal(current) and current != target:
            from .errors import AgentRuntimeInvalidTransitionError

            raise AgentRuntimeInvalidTransitionError(
                f"Cannot transition terminal step state {current.value} to {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        return target


__all__ = [
    "AGENT_LOOP_TERMINAL",
    "AgentLoopLifecycle",
    "AgentLoopState",
    "SESSION_TERMINAL",
    "STEP_TERMINAL",
    "SessionLifecycle",
    "SessionState",
    "StepLifecycle",
    "StepState",
    "TASK_TERMINAL",
    "TaskLifecycle",
    "TaskState",
    "WORKFLOW_TERMINAL",
    "WorkflowLifecycle",
    "WorkflowState",
]
