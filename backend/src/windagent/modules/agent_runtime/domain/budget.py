"""Budget limits/usage/snapshot (Phase 13).

Ports ``windagent_core.domain.agent_loop`` budget types onto V2 kernel
Pydantic models.  Limits are immutable; inheritance is component-wise minimum
(child may only tighten finite limits).  Exhaustion detection is fail-closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BudgetScope(StrEnum):
    CONVERSATION = "conversation"
    PARENT_RUN = "parent_run"
    TASK_NODE = "task_node"
    CHILD = "child"
    TOOL = "tool"


class AgentBudgetLimits(BaseModel):
    """Immutable serializable limits. ``None`` means unlimited."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_turns: int | None = Field(default=None, ge=0)
    max_wall_time_seconds: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_model_failures: int | None = Field(default=None, ge=0)
    max_tool_failures: int | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_child_agents: int | None = Field(default=None, ge=0)
    max_recursion_depth: int | None = Field(default=None, ge=0)


class AgentBudgetUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    turns: int = Field(default=0, ge=0)
    wall_time_seconds: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    model_failures: int = Field(default=0, ge=0)
    tool_failures: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    child_agents: int = Field(default=0, ge=0)
    recursion_depth: int = Field(default=0, ge=0)


class AgentBudgetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_run_id: str = Field(min_length=1)
    scope: BudgetScope = BudgetScope.CONVERSATION
    limits: AgentBudgetLimits = Field(default_factory=AgentBudgetLimits)
    usage: AgentBudgetUsage = Field(default_factory=AgentBudgetUsage)
    exhaustion_reason: str | None = None
    version: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    updated_at: datetime | None = None

    def is_exhausted(self) -> str | None:
        """Return exhaustion reason if any limit is breached, else None."""
        lim = self.limits
        u = self.usage
        if lim.max_turns is not None and u.turns >= lim.max_turns:
            return "max_turns"
        if lim.max_wall_time_seconds is not None and u.wall_time_seconds >= lim.max_wall_time_seconds:
            return "max_wall_time_seconds"
        if lim.max_tokens is not None and u.tokens >= lim.max_tokens:
            return "max_tokens"
        if lim.max_cost_usd is not None and u.cost_usd >= lim.max_cost_usd:
            return "max_cost_usd"
        if lim.max_model_failures is not None and u.model_failures >= lim.max_model_failures:
            return "max_model_failures"
        if lim.max_tool_failures is not None and u.tool_failures >= lim.max_tool_failures:
            return "max_tool_failures"
        if lim.max_retries is not None and u.retries >= lim.max_retries:
            return "max_retries"
        if lim.max_child_agents is not None and u.child_agents >= lim.max_child_agents:
            return "max_child_agents"
        if lim.max_recursion_depth is not None and u.recursion_depth >= lim.max_recursion_depth:
            return "max_recursion_depth"
        return None


def clamp_limits(limits: AgentBudgetLimits | dict[str, Any] | None) -> AgentBudgetLimits:
    if isinstance(limits, AgentBudgetLimits):
        return limits
    if isinstance(limits, dict):
        # Filter to known fields; ignore extras
        allowed = set(AgentBudgetLimits.model_fields)
        filtered = {k: v for k, v in limits.items() if k in allowed}
        return AgentBudgetLimits(**filtered)
    return AgentBudgetLimits()


def inherit_limits(parent: AgentBudgetLimits, child: AgentBudgetLimits | dict[str, Any] | None) -> AgentBudgetLimits:
    """Component-wise minimum: child may only tighten finite parent limits."""
    child_clamped = clamp_limits(child)
    merged: dict[str, Any] = {}
    for field in AgentBudgetLimits.model_fields:
        p_val: Any = getattr(parent, field)
        c_val: Any = getattr(child_clamped, field)
        if p_val is None and c_val is None:
            merged[field] = None
        elif p_val is None:
            merged[field] = c_val
        elif c_val is None:
            merged[field] = p_val
        else:
            # Both finite → minimum wins (tighter)
            if isinstance(p_val, float) or isinstance(c_val, float):
                merged[field] = min(float(p_val), float(c_val))
            else:
                merged[field] = min(int(p_val), int(c_val))
    return AgentBudgetLimits(**merged)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "AgentBudgetLimits",
    "AgentBudgetSnapshot",
    "AgentBudgetUsage",
    "BudgetScope",
    "clamp_limits",
    "inherit_limits",
]
