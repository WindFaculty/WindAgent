"""Durable agent-loop state machine & persisted budget controller (Phase 2).

Implements:
- 12-state durable loop with explicit legal/terminal transitions
- Immutable serializable limits/usage/snapshots covering all budget dimensions
- Inheritance as component-wise minimum (child may only tighten finite limits)
- Exhaustion detection that fails closed
- CAS-safe transition helpers reusing existing exception hierarchy

Domain layer has no SQL; persistence lives in storage.
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


# ─────────────────────────────────────────────────────────────────────
# Loop state machine
# ─────────────────────────────────────────────────────────────────────


class AgentLoopState(str, Enum):
    """Durable agent-run loop states (Phase 2 §7)."""

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


class BudgetScope(str, Enum):
    """Scope at which a budget snapshot was derived."""

    CONVERSATION = "conversation"
    PARENT_RUN = "parent_run"
    TASK_NODE = "task_node"
    CHILD = "child"
    TOOL = "tool"


TERMINAL_LOOP_STATES: Set[AgentLoopState] = {
    AgentLoopState.COMPLETED,
    AgentLoopState.FAILED,
    AgentLoopState.CANCELLED,
    AgentLoopState.ORPHANED,
}

LEGAL_LOOP_TRANSITIONS: Dict[AgentLoopState, Set[AgentLoopState]] = {
    AgentLoopState.CREATED: {
        AgentLoopState.READY,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.READY: {
        AgentLoopState.RUNNING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.RUNNING: {
        AgentLoopState.WAITING_TOOL,
        AgentLoopState.WAITING_CHILD,
        AgentLoopState.WAITING_SCHEDULE,
        AgentLoopState.COMPACTING,
        AgentLoopState.PAUSED,
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.WAITING_TOOL: {
        AgentLoopState.RUNNING,
        AgentLoopState.PAUSED,
        AgentLoopState.COMPACTING,
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.WAITING_CHILD: {
        AgentLoopState.RUNNING,
        AgentLoopState.PAUSED,
        AgentLoopState.COMPACTING,
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.WAITING_SCHEDULE: {
        AgentLoopState.RUNNING,
        AgentLoopState.PAUSED,
        AgentLoopState.COMPACTING,
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.COMPACTING: {
        AgentLoopState.RUNNING,
        AgentLoopState.PAUSED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.PAUSED: {
        AgentLoopState.RUNNING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    },
    AgentLoopState.COMPLETED: set(),
    AgentLoopState.FAILED: set(),
    AgentLoopState.CANCELLED: set(),
    AgentLoopState.ORPHANED: set(),
}


class AgentLoopTransitionResult(BaseModel):
    """Result emitted after a successful durable loop transition."""

    aggregate_id: str
    from_state: str
    to_state: str
    previous_version: int
    new_version: int
    occurred_at: datetime = Field(default_factory=utc_now)
    reason: Optional[str] = None

    model_config = ConfigDict(frozen=True, extra="forbid")


class LoopTransitionResult(AgentLoopTransitionResult):
    """Alias for backward compat."""


class AgentLoopLifecycle:
    """CAS-guarded state machine for the durable loop."""

    TERMINAL_STATES = TERMINAL_LOOP_STATES
    LEGAL_TRANSITIONS = LEGAL_LOOP_TRANSITIONS

    @classmethod
    def is_terminal(cls, state: AgentLoopState | str) -> bool:
        if isinstance(state, str):
            try:
                state = AgentLoopState(state)
            except ValueError:
                return False
        return state in cls.TERMINAL_STATES

    @classmethod
    def can_transition(cls, current: AgentLoopState | str, target: AgentLoopState | str) -> bool:
        if isinstance(current, str):
            current = AgentLoopState(current)
        if isinstance(target, str):
            target = AgentLoopState(target)
        if current == target:
            return True
        return target in cls.LEGAL_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: AgentLoopState, target: AgentLoopState) -> None:
        if cls.is_terminal(current):
            raise TerminalStateMutationError(
                f"Cannot transition terminal loop state {current.value} to {target.value}"
            )
        if not cls.can_transition(current, target):
            allowed = sorted(s.value for s in cls.LEGAL_TRANSITIONS.get(current, set()))
            raise InvalidStateTransitionError(
                f"Illegal loop transition from {current.value} to {target.value}. Allowed: {allowed}"
            )

    @classmethod
    def transition(
        cls,
        *,
        aggregate_id: str | None = None,
        agent_run_id: str | None = None,
        current: AgentLoopState | str,
        target: AgentLoopState | str,
        current_version: int,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> AgentLoopTransitionResult:
        agg = aggregate_id or agent_run_id or "aggregate"
        curr = current if isinstance(current, AgentLoopState) else AgentLoopState(str(current).upper())
        targ = target if isinstance(target, AgentLoopState) else AgentLoopState(str(target).upper())
        if expected_version is not None and expected_version != current_version:
            raise ConcurrentStateConflictError(
                f"Concurrent modification for AgentLoop {agg}: expected version {expected_version}, actual version {current_version}"
            )
        if curr == targ:
            return AgentLoopTransitionResult(
                aggregate_id=agg,
                from_state=curr.value,
                to_state=targ.value,
                previous_version=current_version,
                new_version=current_version,
                reason=reason,
            )
        cls.validate_transition(curr, targ)
        return AgentLoopTransitionResult(
            aggregate_id=agg,
            from_state=curr.value,
            to_state=targ.value,
            previous_version=current_version,
            new_version=current_version + 1,
            reason=reason,
        )


# ─────────────────────────────────────────────────────────────────────
# Budget types
# ─────────────────────────────────────────────────────────────────────


class AgentBudgetLimits(BaseModel):
    """Immutable serializable limits. ``None`` means unlimited."""

    max_turns: Optional[int] = Field(default=None, ge=0)
    max_wall_time_seconds: Optional[int] = Field(default=None, ge=0)
    max_tokens: Optional[int] = Field(default=None, ge=0)
    max_cost_usd: Optional[float] = Field(default=None, ge=0)
    max_model_failures: Optional[int] = Field(default=None, ge=0)
    max_tool_failures: Optional[int] = Field(default=None, ge=0)
    max_retries: Optional[int] = Field(default=None, ge=0)
    max_child_agents: Optional[int] = Field(default=None, ge=0)
    max_recursion_depth: Optional[int] = Field(default=None, ge=0)
    max_parallel_children: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentBudgetUsage(BaseModel):
    """Durable usage counters for a run."""

    turns_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    cost_used: float = Field(default=0.0, ge=0)
    model_failures: int = Field(default=0, ge=0)
    tool_failures: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    child_agents_spawned: int = Field(default=0, ge=0)
    recursion_depth: int = Field(default=0, ge=0)
    parallel_children_current: int = Field(default=0, ge=0)
    parallel_children_max_observed: int = Field(default=0, ge=0)

    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentBudgetSnapshot(BaseModel):
    """Immutable serializable budget snapshot persisted per run."""

    agent_run_id: str
    scope: BudgetScope = Field(default=BudgetScope.CONVERSATION)
    limits: AgentBudgetLimits = Field(default_factory=AgentBudgetLimits)
    usage: AgentBudgetUsage = Field(default_factory=AgentBudgetUsage)
    exhaustion_reason: Optional[str] = Field(default=None)
    version: int = Field(default=1, ge=1)
    started_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)

    model_config = ConfigDict(frozen=True, extra="forbid")

    def is_exhausted(self, now: Optional[datetime] = None) -> Optional[str]:
        """Return exhaustion reason if exhausted, otherwise None. Fail-closed."""
        now = now or utc_now()
        lim = self.limits
        use = self.usage
        if lim.max_turns is not None and use.turns_used >= lim.max_turns:
            return "max_turns_exhausted"
        if lim.max_tokens is not None and use.tokens_used >= lim.max_tokens:
            return "max_tokens_exhausted"
        if lim.max_cost_usd is not None and use.cost_used >= lim.max_cost_usd:
            return "max_cost_exhausted"
        if lim.max_model_failures is not None and use.model_failures >= lim.max_model_failures:
            return "max_model_failures_exhausted"
        if lim.max_tool_failures is not None and use.tool_failures >= lim.max_tool_failures:
            return "max_tool_failures_exhausted"
        if lim.max_retries is not None and use.retries_used >= lim.max_retries:
            return "max_retries_exhausted"
        if lim.max_child_agents is not None and use.child_agents_spawned >= lim.max_child_agents:
            return "max_child_agents_exhausted"
        if lim.max_recursion_depth is not None and use.recursion_depth >= lim.max_recursion_depth:
            return "max_recursion_depth_exhausted"
        if lim.max_parallel_children is not None and use.parallel_children_current >= lim.max_parallel_children:
            return "max_parallel_children_exhausted"
        if lim.max_wall_time_seconds is not None and self.started_at is not None:
            elapsed = (now - self.started_at).total_seconds()
            if elapsed >= float(lim.max_wall_time_seconds):
                return "max_wall_time_exhausted"
        if self.exhaustion_reason is not None:
            return self.exhaustion_reason
        return None

    def has_remaining(self, now: Optional[datetime] = None) -> bool:
        return self.is_exhausted(now) is None


def clamp_limits(
    parent: AgentBudgetLimits, child_requested: AgentBudgetLimits
) -> AgentBudgetLimits:
    """Component-wise minimum: child may only tighten a finite inherited limit."""

    def _clamp(p: Any, c: Any) -> Any:
        if p is None:
            return c
        if c is None:
            return p
        try:
            return min(p, c)
        except TypeError:
            return p if p < c else c

    return AgentBudgetLimits(
        max_turns=_clamp(parent.max_turns, child_requested.max_turns),
        max_wall_time_seconds=_clamp(parent.max_wall_time_seconds, child_requested.max_wall_time_seconds),
        max_tokens=_clamp(parent.max_tokens, child_requested.max_tokens),
        max_cost_usd=_clamp(parent.max_cost_usd, child_requested.max_cost_usd),
        max_model_failures=_clamp(parent.max_model_failures, child_requested.max_model_failures),
        max_tool_failures=_clamp(parent.max_tool_failures, child_requested.max_tool_failures),
        max_retries=_clamp(parent.max_retries, child_requested.max_retries),
        max_child_agents=_clamp(parent.max_child_agents, child_requested.max_child_agents),
        max_recursion_depth=_clamp(parent.max_recursion_depth, child_requested.max_recursion_depth),
        max_parallel_children=_clamp(parent.max_parallel_children, child_requested.max_parallel_children),
    )


def inherit_snapshot(
    *,
    parent_snapshot: AgentBudgetSnapshot,
    child_agent_run_id: str,
    child_requested_limits: AgentBudgetLimits | None = None,
    child_scope: BudgetScope = BudgetScope.CHILD,
) -> AgentBudgetSnapshot:
    """Derive a child snapshot as clamped minimum; usage resets except recursion depth."""
    requested = child_requested_limits or AgentBudgetLimits()
    effective = clamp_limits(parent_snapshot.limits, requested)
    child_depth = int(parent_snapshot.usage.recursion_depth) + 1
    usage = AgentBudgetUsage(
        recursion_depth=child_depth,
    )
    return AgentBudgetSnapshot(
        agent_run_id=child_agent_run_id,
        scope=child_scope,
        limits=effective,
        usage=usage,
        version=1,
        started_at=utc_now(),
        updated_at=utc_now(),
    )


__all__ = [
    "AgentLoopState",
    "BudgetScope",
    "AgentBudgetLimits",
    "AgentBudgetUsage",
    "AgentBudgetSnapshot",
    "AgentLoopLifecycle",
    "AgentLoopTransitionResult",
    "LoopTransitionResult",
    "TERMINAL_LOOP_STATES",
    "LEGAL_LOOP_TRANSITIONS",
    "clamp_limits",
    "inherit_snapshot",
]
