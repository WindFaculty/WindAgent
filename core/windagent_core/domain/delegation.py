"""Durable recursive subagent delegation domain (Phase 4)."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from pydantic import BaseModel, ConfigDict, Field
from windagent_core.domain.agent_loop import AgentBudgetLimits, clamp_limits
def utc_now() -> datetime:
    return datetime.now(timezone.utc)
class ChildFailurePolicy(str, Enum):
    RETRY = "retry"
    REPLACE = "replace"
    PARTIAL_SUCCESS = "partial_success"
    SKIP = "skip"
    ESCALATE = "escalate"
    FAIL_PARENT = "fail_parent"
class DelegationContext(BaseModel):
    goal: str = Field(description="High-level objective")
    subtask: str = Field(description="Specific child objective")
    relevant_artifacts: tuple[str, ...] = Field(default_factory=tuple)
    selected_memory: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    policy: dict[str, Any] = Field(default_factory=dict)
    skills: tuple[str, ...] = Field(default_factory=tuple)
    allocated_budget: AgentBudgetLimits | None = Field(default=None)
    model_config = ConfigDict(frozen=True, extra="forbid")
    def validate_bounded(self) -> None:
        if not self.goal or not self.goal.strip():
            raise ValueError("goal must not be empty")
        if not self.subtask or not self.subtask.strip():
            raise ValueError("subtask must not be empty")
class DelegationHandle(BaseModel):
    child_agent_run_id: str
    parent_agent_run_id: str
    root_agent_run_id: str
    delegation_depth: int
    delegation_reason: str
    allocated_budget: AgentBudgetLimits | None = None
    failure_policy: ChildFailurePolicy = Field(default=ChildFailurePolicy.FAIL_PARENT)
    model_config = ConfigDict(frozen=True, extra="forbid")
class DelegationRecord(BaseModel):
    child_agent_run_id: str
    parent_agent_run_id: str
    root_agent_run_id: str
    delegation_depth: int = Field(ge=1)
    delegation_reason: str
    failure_policy: ChildFailurePolicy = Field(default=ChildFailurePolicy.FAIL_PARENT)
    allocated_budget: AgentBudgetLimits | None = None
    child_result_summary: dict[str, Any] | None = Field(default=None)
    child_artifact_refs: tuple[str, ...] = Field(default_factory=tuple)
    bounded_context: dict[str, Any] | None = Field(default=None)
    version: int = Field(default=1, ge=1)
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
    model_config = ConfigDict(frozen=True, extra="forbid")
class DelegationSummary(BaseModel):
    child_agent_run_id: str
    parent_agent_run_id: str
    status: str = Field(description="Child terminal status")
    summary_text: str = Field(default="")
    artifact_refs: tuple[str, ...] = Field(default_factory=tuple)
    metrics: dict[str, Any] | None = Field(default=None)
    model_config = ConfigDict(frozen=True, extra="forbid")
def resolve_root_and_depth(parent_record: DelegationRecord | None, parent_agent_run_id: str) -> tuple[str, int]:
    if parent_record is None:
        return parent_agent_run_id, 1
    return parent_record.root_agent_run_id, int(parent_record.delegation_depth) + 1
def clamp_child_budget(parent_limits: AgentBudgetLimits, requested: AgentBudgetLimits | Mapping[str, Any] | None) -> AgentBudgetLimits:
    if isinstance(requested, Mapping) and not isinstance(requested, AgentBudgetLimits):
        req = AgentBudgetLimits(**{k: v for k, v in requested.items() if k in AgentBudgetLimits.model_fields})
    elif isinstance(requested, AgentBudgetLimits):
        req = requested
    else:
        req = AgentBudgetLimits()
    return clamp_limits(parent_limits, req)
def project_bounded_context(*, goal: str, subtask: str, relevant_artifacts: tuple[str, ...] | list[str] | None = None, selected_memory: tuple[dict[str, Any], ...] | list[dict[str, Any]] | None = None, policy: Mapping[str, Any] | None = None, skills: tuple[str, ...] | list[str] | None = None, allocated_budget: AgentBudgetLimits | None = None) -> DelegationContext:
    ctx = DelegationContext(goal=goal.strip(), subtask=subtask.strip(), relevant_artifacts=tuple(relevant_artifacts or ()), selected_memory=tuple(selected_memory or ()), policy=dict(policy or {}), skills=tuple(skills or ()), allocated_budget=allocated_budget)
    ctx.validate_bounded()
    if len(ctx.selected_memory) > 20:
        raise ValueError("selected_memory bounded to 20")
    if len(ctx.relevant_artifacts) > 20:
        raise ValueError("relevant_artifacts bounded to 20")
    if len(ctx.skills) > 20:
        raise ValueError("skills bounded to 20")
    return ctx
__all__ = ["ChildFailurePolicy","DelegationContext","DelegationHandle","DelegationRecord","DelegationSummary","resolve_root_and_depth","clamp_child_budget","project_bounded_context"]
