"""Phase 6 — Schemas for memory-aware routing metadata."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class MemoryRoutingContext(BaseModel):
    """Memory context passed by agents into the router for scoring adjustments."""

    memory_required: bool = False
    """Whether this request requires memory retrieval."""

    memory_scope: Literal["session", "project", "global"] = "session"
    """Scope of memory needed: session-local, project-wide, or global."""

    retrieval_budget_tokens: int = Field(default=512, ge=0, le=8192)
    """Maximum number of tokens allocated for memory retrieval content."""

    writeback_policy: Literal["none", "summary", "full"] = "none"
    """How the result should be written back to memory after the request."""


class MemoryRoutingDecision(BaseModel):
    """Decision output for memory-aware routing."""

    selected_profile: str
    """Profile or model tier selected, e.g. 'primary', 'memory_enhanced', 'degraded'."""

    memory_satisfied: bool
    """Whether memory requirements could be fulfilled."""

    degraded: bool = False
    """True if memory was required but unavailable — request proceeds in degraded mode."""

    reason: str = ""
    """Human-readable reason for the decision."""
