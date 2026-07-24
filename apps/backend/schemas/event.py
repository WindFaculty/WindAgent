"""Pydantic schemas for event envelope and per-event payloads.

Shape MUST match docs/event_protocol.md exactly.
If you change a field here, update the doc in the same commit.

Phase 14: backend keeps a legacy-compatible envelope (fields: event,
timestamp, data, seq, sequence) while the canonical envelope lives in
``windagent_core.events.envelope``.  ``EventEnvelope`` here is an alias
for the legacy class so existing routers/services/tests keep compiling.
Hooks that need canonical events call ``to_canonical()``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.types import EventId, SessionId
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.envelope import EventEnvelope as CanonicalEventEnvelope


# ---------- Legacy Envelope (backend internal protocol) ----------

EventName = Literal[
    "session_created",
    "session_finished",
    "message_received",
    "planning_started",
    "planning_finished",
    "workflow_created",
    "workflow_updated",
    "step_started",
    "step_completed",
    "step_failed",
    "step_cancelled",
    "tool_call_started",
    "tool_call_finished",
    "permission_request",
    "permission_granted",
    "permission_denied",
    "agent_s3_action_proposed",
    "user_paused",
    "user_resumed",
    "user_stopped",
    "error",
    "assistant_message_started",
    "assistant_message_delta",
    "assistant_message_completed",
    "reasoning_delta",
    "tool_call_progress",
    "terminal_output",
    "artifact_created",
    "clarification_request",
    "worktree_created",
    "worktree_changed",
    "worktree_committed",
    "worktree_merged",
    "worktree_conflict",
    "worktree_removed",
    "replan_notification",
    "browser_session_started",
    "browser_navigation_started",
    "browser_navigation_completed",
    "browser_screenshot_updated",
    "browser_action_started",
    "browser_action_completed",
    "browser_console",
    "browser_error",
]


# Mapping from legacy camel/snake event names to canonical dotted taxonomy.
_LEGACY_TO_CANONICAL: Dict[str, str] = {
    "session_created": EventCatalog.SESSION_CREATED,
    "session_finished": EventCatalog.SESSION_FINISHED,
    "message_received": EventCatalog.SESSION_MESSAGE_RECEIVED,
    "planning_started": EventCatalog.PLANNING_STARTED,
    "planning_finished": EventCatalog.PLANNING_FINISHED,
    "workflow_created": EventCatalog.WORKFLOW_CREATED,
    "workflow_updated": EventCatalog.WORKFLOW_UPDATED,
    "step_started": EventCatalog.STEP_STARTED,
    "step_completed": EventCatalog.STEP_COMPLETED,
    "step_failed": EventCatalog.STEP_FAILED,
    "step_cancelled": EventCatalog.STEP_CANCELLED,
    "tool_call_started": EventCatalog.TOOL_STARTED,
    "tool_call_finished": EventCatalog.TOOL_FINISHED,
    "permission_request": EventCatalog.PERMISSION_REQUESTED,
    "permission_granted": EventCatalog.PERMISSION_GRANTED,
    "permission_denied": EventCatalog.PERMISSION_DENIED,
    "agent_s3_action_proposed": EventCatalog.TOOL_AGENT_S3_ACTION_PROPOSED,
    "user_paused": EventCatalog.SESSION_PAUSED,
    "user_resumed": EventCatalog.SESSION_RESUMED,
    "user_stopped": EventCatalog.SESSION_STOPPED,
    "error": EventCatalog.SYSTEM_ERROR,
    "assistant_message_started": EventCatalog.SESSION_ASSISTANT_STARTED,
    "assistant_message_delta": EventCatalog.SESSION_ASSISTANT_DELTA,
    "assistant_message_completed": EventCatalog.SESSION_ASSISTANT_COMPLETED,
    "reasoning_delta": EventCatalog.MODEL_REASONING_DELTA,
    "tool_call_progress": EventCatalog.TOOL_PROGRESS,
    "terminal_output": "system.terminal_output",
    "artifact_created": EventCatalog.ARTIFACT_CREATED,
    "clarification_request": EventCatalog.PLANNING_CLARIFICATION_REQUEST,
    "worktree_created": EventCatalog.WORKTREE_CREATED,
    "worktree_changed": EventCatalog.WORKTREE_CHANGED,
    "worktree_committed": EventCatalog.WORKTREE_COMMITTED,
    "worktree_merged": EventCatalog.WORKTREE_MERGED,
    "worktree_conflict": EventCatalog.WORKTREE_CONFLICT,
    "worktree_removed": EventCatalog.WORKTREE_REMOVED,
    "replan_notification": EventCatalog.PLANNING_REPLAN,
    "browser_session_started": EventCatalog.BROWSER_SESSION_STARTED,
    "browser_navigation_started": EventCatalog.BROWSER_NAV_STARTED,
    "browser_navigation_completed": EventCatalog.BROWSER_NAV_COMPLETED,
    "browser_screenshot_updated": EventCatalog.BROWSER_SCREENSHOT_UPDATED,
    "browser_action_started": EventCatalog.BROWSER_ACTION_STARTED,
    "browser_action_completed": EventCatalog.BROWSER_ACTION_COMPLETED,
    "browser_console": EventCatalog.BROWSER_CONSOLE,
    "browser_error": EventCatalog.BROWSER_ERROR,
}


class LegacyEventEnvelope(BaseModel):
    """Backend-internal event envelope compatible with Phase 1-5 protocol.

    Immutable enough for in-memory fan-out; the canonical representation
    is produced on demand via ``to_canonical()``.
    """

    event: EventName
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = Field(default_factory=dict)
    seq: int = Field(default=0)
    sequence: int = Field(default=0)

    model_config = ConfigDict(frozen=True, extra="forbid")

    def to_canonical(
        self,
        session_id: Optional[SessionId] = None,
        aggregate_id: Optional[str] = None,
        aggregate_type: Optional[str] = None,
    ) -> CanonicalEventEnvelope:
        event_type = _LEGACY_TO_CANONICAL.get(self.event, self.event)
        return CanonicalEventEnvelope(
            event_id=EventId.generate(),
            event_type=event_type,
            session_id=session_id,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            sequence=self.seq or self.sequence,
            payload=self.data,
        )


# Public alias used by existing backend services/tests.
EventEnvelope = LegacyEventEnvelope


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


class AgentS3ActionProposedData(BaseModel):
    """Phase 12 — emitted once per ``agent_s3_step`` invocation,
    after Agent-S3 proposes + WindAgent translates the raw action.

    Carries the **decision** (accepted vs rejected) plus the
    translated tool + params (or rejection reason). Never includes
    API keys, raw screenshot bytes, or secrets.
    """

    session_id: UUID
    step_id: UUID
    instruction: str
    translated_tool: Optional[str] = None
    translated_params: Optional[Dict[str, Any]] = None
    safety_status: Literal["accepted", "rejected"]
    rejection_code: Optional[str] = None
    rejected_count: int = 0
    dry_run: bool = False
    screenshot_path: Optional[str] = None
