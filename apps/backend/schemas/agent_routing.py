"""Phase 6 — Schemas for Agent-to-Agent routing and capability registry."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


AgentRole = Literal["Planner", "Coder", "GUI", "Workflow", "Research", "Memory"]


class AgentCapability(BaseModel):
    """Describes capabilities of a registered agent."""

    role: AgentRole
    """The role identifier of the agent."""

    task_types: List[str] = Field(default_factory=list)
    """Task type identifiers this agent can handle (e.g. 'code_generation', 'research')."""

    model_requirements: Dict[str, Any] = Field(default_factory=dict)
    """Minimum model properties required (e.g. {'context_window': 8192})."""

    tool_permissions: List[str] = Field(default_factory=list)
    """Tools or permissions this agent is allowed to use."""

    max_latency_ms: int = Field(default=10000, ge=0)
    """Maximum acceptable latency in milliseconds for this agent's tasks."""

    cost_priority: Literal["low", "medium", "high"] = "medium"
    """Cost sensitivity: low means cheapest model preferred."""

    supports_delegation: bool = True
    """Whether this agent can accept delegated tasks from other agents."""


class DelegationRequest(BaseModel):
    """Request to delegate a task to another agent."""

    from_role: AgentRole
    """The role of the agent initiating delegation."""

    to_role: AgentRole
    """The target agent role to delegate to."""

    task_type: str
    """The type of task being delegated."""

    prompt: str
    """The task prompt to be executed by the delegated agent."""

    context: Optional[str] = None
    """Optional context to pass along with the delegation."""

    depth: int = Field(default=0, ge=0, le=10)
    """Current delegation depth — used to enforce max depth guard."""


class DelegationResponse(BaseModel):
    """Response from a delegated agent execution."""

    success: bool
    """Whether the delegation completed successfully."""

    result: Optional[str] = None
    """The output returned by the delegated agent."""

    error: Optional[str] = None
    """Error message if the delegation failed."""

    executed_by: AgentRole
    """The role that actually executed the task."""

    depth: int = 0
    """Depth at which this delegation occurred."""

    delegation_chain: List[str] = Field(default_factory=list)
    """Chain of roles that were traversed to reach the executor."""
