"""Immutable hierarchical budget types (ban_ke_hoach_v1 §7 Phase 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BudgetLimits(BaseModel):
    max_turns: int | None = Field(default=None, ge=0)
    max_wall_time_seconds: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_model_failures: int | None = Field(default=None, ge=0)
    max_tool_failures: int | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_child_agents: int | None = Field(default=None, ge=0)
    max_recursion_depth: int | None = Field(default=None, ge=0)
    max_parallel_children: int | None = Field(default=None, ge=0)
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator(
        "max_turns",
        "max_wall_time_seconds",
        "max_tokens",
        "max_model_failures",
        "max_tool_failures",
        "max_retries",
        "max_child_agents",
        "max_recursion_depth",
        "max_parallel_children",
        mode="before",
    )
    @classmethod
    def _validate_int_limits(cls, v: Any) -> Any:
        if v is None:
            return None
        iv = int(v)
        if iv < 0:
            raise ValueError("budget limit must be >= 0")
        return iv

    @field_validator("max_cost_usd", mode="before")
    @classmethod
    def _validate_cost(cls, v: Any) -> Any:
        if v is None:
            return None
        fv = float(v)
        if fv < 0:
            raise ValueError("budget limit must be >= 0")
        return fv


class BudgetUsage(BaseModel):
    turns_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    cost_used: float = Field(default=0.0, ge=0)
    model_failures: int = Field(default=0, ge=0)
    tool_failures: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    child_agents_used: int = Field(default=0, ge=0)
    recursion_depth_used: int = Field(default=0, ge=0)
    parallel_children_used: int = Field(default=0, ge=0)
    model_config = ConfigDict(frozen=True, extra="forbid")


class BudgetScope(BaseModel):
    conversation_id: str | None = None
    parent_run_id: str | None = None
    task_node_run_id: str | None = None
    agent_run_id: str | None = None
    model_config = ConfigDict(frozen=True, extra="forbid")


class BudgetSnapshot(BaseModel):
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
    usage: BudgetUsage = Field(default_factory=BudgetUsage)
    scope: BudgetScope = Field(default_factory=BudgetScope)
    wall_time_started_at: datetime | None = Field(default=None)
    exhaustion_reason: str | None = Field(default=None)
    version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=utc_now)
    model_config = ConfigDict(frozen=True, extra="forbid")

    def wall_elapsed_seconds(self, now: datetime | None = None) -> int | None:
        if self.wall_time_started_at is None:
            return None
        n = now or utc_now()
        start = self.wall_time_started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        delta = (n - start).total_seconds()
        return int(delta) if delta >= 0 else 0


def check_exhaustion(
    snapshot: BudgetSnapshot, *, now: datetime | None = None
) -> str | None:
    limits = snapshot.limits
    usage = snapshot.usage
    if limits.max_turns is not None and usage.turns_used >= limits.max_turns:
        return "max_turns_exhausted"
    if limits.max_tokens is not None and usage.tokens_used >= limits.max_tokens:
        return "max_tokens_exhausted"
    if limits.max_cost_usd is not None and usage.cost_used >= limits.max_cost_usd:
        return "max_cost_exhausted"
    if (
        limits.max_model_failures is not None
        and usage.model_failures >= limits.max_model_failures
    ):
        return "max_model_failures_exhausted"
    if (
        limits.max_tool_failures is not None
        and usage.tool_failures >= limits.max_tool_failures
    ):
        return "max_tool_failures_exhausted"
    if limits.max_retries is not None and usage.retries_used >= limits.max_retries:
        return "max_retries_exhausted"
    if (
        limits.max_child_agents is not None
        and usage.child_agents_used >= limits.max_child_agents
    ):
        return "max_child_agents_exhausted"
    if (
        limits.max_recursion_depth is not None
        and usage.recursion_depth_used >= limits.max_recursion_depth
    ):
        return "max_recursion_depth_exhausted"
    if (
        limits.max_parallel_children is not None
        and usage.parallel_children_used >= limits.max_parallel_children
    ):
        return "max_parallel_children_exhausted"
    if limits.max_wall_time_seconds is not None:
        elapsed = snapshot.wall_elapsed_seconds(now)
        if elapsed is not None and elapsed >= limits.max_wall_time_seconds:
            return "max_wall_time_exhausted"
    return None


def is_exhausted(snapshot: BudgetSnapshot, *, now: datetime | None = None) -> bool:
    return check_exhaustion(snapshot, now=now) is not None


def _clamp_value(
    parent: int | float | None, child: int | float | None
) -> int | float | None:
    if parent is None:
        return child
    if child is None:
        return parent
    return min(parent, child)  # type: ignore[return-value]


def derive_child_limits(
    parent: BudgetLimits, requested: BudgetLimits | None
) -> BudgetLimits:
    if requested is None:
        return parent
    return BudgetLimits(
        max_turns=_clamp_value(parent.max_turns, requested.max_turns),
        max_wall_time_seconds=_clamp_value(
            parent.max_wall_time_seconds, requested.max_wall_time_seconds
        ),
        max_tokens=_clamp_value(parent.max_tokens, requested.max_tokens),
        max_cost_usd=_clamp_value(parent.max_cost_usd, requested.max_cost_usd),
        max_model_failures=_clamp_value(
            parent.max_model_failures, requested.max_model_failures
        ),
        max_tool_failures=_clamp_value(
            parent.max_tool_failures, requested.max_tool_failures
        ),
        max_retries=_clamp_value(parent.max_retries, requested.max_retries),
        max_child_agents=_clamp_value(
            parent.max_child_agents, requested.max_child_agents
        ),
        max_recursion_depth=_clamp_value(
            parent.max_recursion_depth, requested.max_recursion_depth
        ),
        max_parallel_children=_clamp_value(
            parent.max_parallel_children, requested.max_parallel_children
        ),
    )


def inherit_limits_chain(
    *,
    conversation: BudgetLimits | None = None,
    parent_run: BudgetLimits | None = None,
    task_node: BudgetLimits | None = None,
    child_requested: BudgetLimits | None = None,
) -> BudgetLimits:
    effective = BudgetLimits()
    for layer in (conversation, parent_run, task_node, child_requested):
        if layer is None:
            continue
        effective = BudgetLimits(
            max_turns=_clamp_value(effective.max_turns, layer.max_turns),
            max_wall_time_seconds=_clamp_value(
                effective.max_wall_time_seconds, layer.max_wall_time_seconds
            ),
            max_tokens=_clamp_value(effective.max_tokens, layer.max_tokens),
            max_cost_usd=_clamp_value(effective.max_cost_usd, layer.max_cost_usd),
            max_model_failures=_clamp_value(
                effective.max_model_failures, layer.max_model_failures
            ),
            max_tool_failures=_clamp_value(
                effective.max_tool_failures, layer.max_tool_failures
            ),
            max_retries=_clamp_value(effective.max_retries, layer.max_retries),
            max_child_agents=_clamp_value(
                effective.max_child_agents, layer.max_child_agents
            ),
            max_recursion_depth=_clamp_value(
                effective.max_recursion_depth, layer.max_recursion_depth
            ),
            max_parallel_children=_clamp_value(
                effective.max_parallel_children, layer.max_parallel_children
            ),
        )
    return effective


__all__ = [
    "BudgetLimits",
    "BudgetUsage",
    "BudgetScope",
    "BudgetSnapshot",
    "check_exhaustion",
    "is_exhausted",
    "derive_child_limits",
    "inherit_limits_chain",
]
