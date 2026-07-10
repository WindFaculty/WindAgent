"""Translates Hermes platform events into WindAgent WebSocket protocol events."""
from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, Optional, Tuple

from schemas.event import EventEnvelope


class HermesEventTranslator:
    """Translates Hermes JSON-RPC/SSE events into the standard WindAgent protocol."""

    @staticmethod
    def translate(
        event: Dict[str, Any],
        windagent_session_id: str,
        sequence: int,
        windagent_request_id: Optional[str] = None,
    ) -> Optional[EventEnvelope]:
        """Translate a Hermes event to a WindAgent EventEnvelope.

        Returns None if the event should not be forwarded.
        """
        event_name = event.get("event")
        ts = event.get("timestamp", datetime.datetime.now(datetime.timezone.utc).timestamp())
        dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)

        mapped_event: Optional[str] = None
        data: Dict[str, Any] = {}

        if event_name == "message.delta" or event_name == "assistant.delta":
            mapped_event = "assistant_message_delta"
            data = {
                "message_id": f"msg_{event.get('run_id') or 'default'}",
                "delta": event.get("delta", ""),
            }
        elif event_name == "reasoning.available":
            mapped_event = "reasoning_delta"
            data = {
                "delta": event.get("text", ""),
            }
        elif event_name == "tool.started":
            mapped_event = "tool_call_started"
            data = {
                "session_id": windagent_session_id,
                "step_id": event.get("tool"), # pseudo step_id
                "tool_name": event.get("tool"),
                "input": {"arguments": event.get("preview") or ""},
            }
        elif event_name == "tool.progress":
            mapped_event = "tool_call_progress"
            data = {
                "session_id": windagent_session_id,
                "step_id": event.get("tool"),
                "tool_name": event.get("tool"),
                "progress": event.get("progress", ""),
            }
        elif event_name == "tool.completed":
            mapped_event = "tool_call_finished"
            data = {
                "session_id": windagent_session_id,
                "step_id": event.get("tool"),
                "tool_name": event.get("tool"),
                "status": "failed" if event.get("error") else "success",
                "duration_ms": int(event.get("duration", 0) * 1000),
                "output": {},
            }
        elif event_name == "approval.request":
            mapped_event = "permission_request"
            data = {
                "session_id": windagent_session_id,
                "step_id": event.get("tool") or "hermes_command",
                "request_id": windagent_request_id or str(uuid.uuid4()),
                "tool_name": event.get("tool") or "terminal",
                "risk_level": "high" if "destructive" in str(event.get("tool")).lower() else "medium",
                "summary": event.get("summary") or f"Execute command: {event.get('command')}",
                "params": {"command": event.get("command") or ""},
            }
        elif event_name == "run.completed":
            mapped_event = "session_finished"
            data = {
                "session_id": windagent_session_id,
                "workflow_id": event.get("run_id"),
                "final_status": "completed",
                "total_duration_ms": 0, # computed dynamically or ignored
                "output": event.get("output", ""),
            }
        elif event_name == "run.failed":
            mapped_event = "session_finished"
            data = {
                "session_id": windagent_session_id,
                "workflow_id": event.get("run_id"),
                "final_status": "failed",
                "total_duration_ms": 0,
                "error": {
                    "type": "run_failed",
                    "message": event.get("error", "Run failed"),
                    "code": "RUN_FAILED"
                }
            }
        elif event_name == "run.cancelled":
            mapped_event = "session_finished"
            data = {
                "session_id": windagent_session_id,
                "workflow_id": event.get("run_id"),
                "final_status": "cancelled",
                "total_duration_ms": 0,
            }
        else:
            return None

        return EventEnvelope(
            event=mapped_event,
            timestamp=dt,
            data=data,
        )
