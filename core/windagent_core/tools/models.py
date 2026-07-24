"""
Canonical Tool Invocation and Result Models for WindAgent Core (Phase 10).
Decoupled shared tool execution payloads using ToolInvocationId, SessionId, and TaskId.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.types import ToolInvocationId, SessionId, TaskId
from windagent_core.domain.lifecycle import utc_now


class ToolInvocation(BaseModel):
    """Canonical model for tool execution requests."""
    invocation_id: ToolInvocationId
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "agent"
    session_id: Optional[SessionId] = None
    task_id: Optional[TaskId] = None
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolResult(BaseModel):
    """Canonical model for tool execution results."""
    invocation_id: ToolInvocationId
    success: bool
    output: str = ""
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")
