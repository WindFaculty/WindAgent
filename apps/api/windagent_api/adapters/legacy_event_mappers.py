"""
Legacy WebSocket Event Compatibility Serializer & Deserializer for WindAgent Architecture V2.
Located at the API edge adapter boundary. Bidirectionally maps EventEnvelope V2 objects
to legacy WebSocket JSON shapes:
{
    "event": "step_started",
    "timestamp": "2026-07-23T05:00:00Z",
    "seq": 123,
    "data": {}
}
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.domain.types import EventId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog

# Bidirectional mapping dictionary between Legacy event names and V2 event types
LEGACY_TO_V2_MAP: Dict[str, str] = {
    "agent_s3_action_proposed": EventCatalog.TOOL_AGENT_S3_ACTION_PROPOSED,
    "artifact_created": EventCatalog.ARTIFACT_CREATED,
    "assistant_message_completed": EventCatalog.SESSION_ASSISTANT_COMPLETED,
    "assistant_message_delta": EventCatalog.SESSION_ASSISTANT_DELTA,
    "assistant_message_started": EventCatalog.SESSION_ASSISTANT_STARTED,
    "browser_action_completed": EventCatalog.BROWSER_ACTION_COMPLETED,
    "browser_action_started": EventCatalog.BROWSER_ACTION_STARTED,
    "browser_console": EventCatalog.BROWSER_CONSOLE,
    "browser_error": EventCatalog.BROWSER_ERROR,
    "browser_navigation_completed": EventCatalog.BROWSER_NAV_COMPLETED,
    "browser_navigation_started": EventCatalog.BROWSER_NAV_STARTED,
    "browser_screenshot_updated": EventCatalog.BROWSER_SCREENSHOT_UPDATED,
    "browser_session_started": EventCatalog.BROWSER_SESSION_STARTED,
    "clarification_request": EventCatalog.PLANNING_CLARIFICATION_REQUEST,
    "error": EventCatalog.SYSTEM_ERROR,
    "message_received": EventCatalog.SESSION_MESSAGE_RECEIVED,
    "permission_denied": EventCatalog.PERMISSION_DENIED,
    "permission_granted": EventCatalog.PERMISSION_GRANTED,
    "permission_request": EventCatalog.PERMISSION_REQUEST,
    "planning_finished": EventCatalog.PLANNING_FINISHED,
    "planning_started": EventCatalog.PLANNING_STARTED,
    "reasoning_delta": EventCatalog.MODEL_REASONING_DELTA,
    "replan_notification": EventCatalog.PLANNING_REPLAN,
    "session_created": EventCatalog.SESSION_CREATED,
    "session_finished": EventCatalog.SESSION_FINISHED,
    "step_cancelled": EventCatalog.STEP_CANCELLED,
    "step_completed": EventCatalog.STEP_COMPLETED,
    "step_failed": EventCatalog.STEP_FAILED,
    "step_started": EventCatalog.STEP_STARTED,
    "terminal_output": EventCatalog.TERMINAL_OUTPUT,
    "tool_call_finished": EventCatalog.TOOL_FINISHED,
    "tool_call_progress": EventCatalog.TOOL_PROGRESS,
    "tool_call_started": EventCatalog.TOOL_STARTED,
    "user_paused": EventCatalog.SESSION_PAUSED,
    "user_resumed": EventCatalog.SESSION_RESUMED,
    "user_stopped": EventCatalog.SESSION_STOPPED,
    "workflow_created": EventCatalog.WORKFLOW_CREATED,
    "workflow_updated": EventCatalog.WORKFLOW_UPDATED,
    "worktree_changed": EventCatalog.WORKTREE_CHANGED,
    "worktree_committed": EventCatalog.WORKTREE_COMMITTED,
    "worktree_conflict": EventCatalog.WORKTREE_CONFLICT,
    "worktree_created": EventCatalog.WORKTREE_CREATED,
    "worktree_merged": EventCatalog.WORKTREE_MERGED,
    "worktree_removed": EventCatalog.WORKTREE_REMOVED,
}

V2_TO_LEGACY_MAP: Dict[str, str] = {v2: legacy for legacy, v2 in LEGACY_TO_V2_MAP.items()}


def v2_event_to_legacy_dict(envelope: EventEnvelope) -> Dict[str, Any]:
    """Converts an EventEnvelope V2 instance into legacy WebSocket event JSON dictionary."""
    legacy_name = V2_TO_LEGACY_MAP.get(envelope.event_type, envelope.event_type.replace(".", "_"))
    return {
        "event": legacy_name,
        "timestamp": envelope.occurred_at.isoformat(),
        "seq": envelope.sequence,
        "data": envelope.payload,
    }


def legacy_dict_to_v2_event(legacy_dict: Dict[str, Any], session_id: Optional[SessionId] = None) -> EventEnvelope:
    """Converts a legacy WebSocket event JSON dictionary into an EventEnvelope V2 instance."""
    raw_event_name = str(legacy_dict.get("event", "system.unknown"))
    v2_event_type = LEGACY_TO_V2_MAP.get(raw_event_name, raw_event_name)

    raw_ts = legacy_dict.get("timestamp")
    if isinstance(raw_ts, str):
        occurred_at = datetime.fromisoformat(raw_ts)
    elif isinstance(raw_ts, datetime):
        occurred_at = raw_ts
    else:
        occurred_at = datetime.now(timezone.utc)

    seq = int(legacy_dict.get("seq", 0))
    payload = legacy_dict.get("data", {})
    if not isinstance(payload, dict):
        payload = {"data": payload}

    sid = session_id or SessionId.generate()

    return EventEnvelope(
        event_id=EventId.generate(),
        event_type=v2_event_type,
        session_id=sid,
        sequence=seq,
        payload=payload,
        schema_version=2,
        occurred_at=occurred_at,
    )
