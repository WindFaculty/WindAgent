"""Pydantic schemas for event envelope and per-event payloads.

Shape MUST match docs/event_protocol.md exactly.
If you change a field here, update the doc in the same commit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------- Envelope ----------

EventName = Literal[
    "session_created",
    "session_finished",
    "message_received",
    "planning_started",
    "planning_finished",
    "workflow_created",
    "step_started",
    "step_completed",
    "step_failed",
    "tool_call_started",
    "tool_call_finished",
    "permission_request",
    "permission_granted",
    "permission_denied",
    "user_paused",
    "user_resumed",
    "user_stopped",
    "error",
]


class EventEnvelope(BaseModel):
    """Top-level shape of every WebSocket event.

    See docs/event_protocol.md §1.
    """

    event: EventName
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any]

    def model_dump_json_compatible(self) -> Dict[str, Any]:
        """Serialize with ISO 8601 timestamp including timezone offset."""
        payload = self.model_dump(mode="json")
        return payload


# ---------- Per-event data payloads ----------
# These are exposed as standalone models so tests can construct events
# without juggling dict literals, and so OpenAPI shows the shape.

class SessionCreatedData(BaseModel):
    session_id: UUID
    created_at: datetime


class MessageReceivedData(BaseModel):
    session_id: UUID
    message_id: UUID
    content: str


class PlanningStartedData(BaseModel):
    session_id: UUID
    message_id: UUID


class PlanningFinishedData(BaseModel):
    session_id: UUID
    message_id: UUID
    model: str
    latency_ms: int
    used_fallback: bool


class WorkflowCreatedData(BaseModel):
    session_id: UUID
    workflow_id: UUID
    step_count: int


class StepStartedData(BaseModel):
    session_id: UUID
    workflow_id: UUID
    step_id: UUID
    step_name: str
    tool_name: str
    order: int


class StepCompletedData(BaseModel):
    session_id: UUID
    workflow_id: UUID
    step_id: UUID
    duration_ms: int


class StepErrorInfo(BaseModel):
    type: str
    message: str
    code: str


class StepFailedData(BaseModel):
    session_id: UUID
    workflow_id: UUID
    step_id: UUID
    error: StepErrorInfo


class ToolCallStartedData(BaseModel):
    session_id: UUID
    step_id: Optional[UUID] = None
    tool_name: str
    input: Dict[str, Any]


class ToolCallFinishedData(BaseModel):
    session_id: UUID
    step_id: Optional[UUID] = None
    tool_name: str
    status: Literal["success", "failed"]
    output: Optional[Dict[str, Any]] = None
    duration_ms: int = 0
    error: Optional[StepErrorInfo] = None


class PermissionRequestData(BaseModel):
    session_id: UUID
    step_id: UUID
    request_id: UUID
    tool_name: str
    risk_level: Literal["safe", "medium", "high"]
    summary: str
    params: Dict[str, Any]


class PermissionDecisionData(BaseModel):
    session_id: UUID
    step_id: UUID
    tool_name: str
    reason: Optional[str] = None  # only for permission_denied


class UserControlData(BaseModel):
    session_id: UUID
    workflow_id: Optional[UUID] = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorInfo(BaseModel):
    type: str
    message: str
    code: str


class ErrorEventData(BaseModel):
    session_id: Optional[UUID] = None
    context: str
    error: ErrorInfo


class SessionFinishedData(BaseModel):
    session_id: UUID
    workflow_id: Optional[UUID] = None
    final_status: Literal["completed", "failed", "cancelled"]
    total_duration_ms: int