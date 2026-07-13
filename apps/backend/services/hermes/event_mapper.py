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
        first_workflow: bool = False,
    ) -> Optional[EventEnvelope]:
        """Translate a Hermes event to a WindAgent EventEnvelope.

        Returns None if the event should not be forwarded.
        """
        event_name = event.get("event")
        ts = event.get("timestamp", datetime.datetime.now(datetime.timezone.utc).timestamp())
        dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)

        mapped_event: Optional[str] = None
        data: Dict[str, Any] = {}

        # Hermes exposes its task plan through the `todo` tool. Each call
        # returns the full ordered list, so we map it to a WindAgent
        # workflow (Current Task panel). First call => workflow_created,
        # subsequent calls => workflow_updated. The bridge passes
        # `first_workflow` so we don't need per-run state here.
        if event_name == "tool.completed" and (event.get("tool") == "todo"):
            items = _extract_todo_list(event.get("output") or {})
            if items is not None:
                return _todo_to_workflow_envelope(
                    items,
                    run_id=event.get("run_id") or "",
                    windagent_session_id=windagent_session_id,
                    dt=dt,
                    first_workflow=first_workflow,
                )

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
        elif event_name and event_name.startswith("browser_"):
            mapped_event = event_name
            data = event.get("data") or event
        else:
            return None

        return EventEnvelope(
            event=mapped_event,
            timestamp=dt,
            data=data,
        )


def _extract_todo_list(output: Any) -> Optional[list]:
    """Pull the todo item list out of a Hermes `todo` tool output.

    Hermes returns the full ordered list on every todo call. The list may
    live under ``items`` / ``tasks`` / ``todos`` or be the output itself.
    Returns None when no list is present so the caller keeps the plain
    tool_call_finished mapping.
    """
    if isinstance(output, list):
        return output
    if not isinstance(output, dict):
        return None
    for key in ("items", "tasks", "todos", "todo"):
        value = output.get(key)
        if isinstance(value, list):
            return value
    return None


def _todo_to_workflow_envelope(
    items: list,
    run_id: str,
    windagent_session_id: str,
    dt: datetime.datetime,
    first_workflow: bool,
) -> EventEnvelope:
    """Translate a Hermes todo list into a workflow_created/updated event.

    ``workflow_id`` is derived from run_id so the store replaces (not
    duplicates) the plan across todo updates. ``objective`` is left empty;
    the frontend falls back to a neutral label when the agent has not
    stated one.
    """
    valid = {"pending", "in_progress", "completed", "cancelled"}
    steps = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "pending")).lower()
        if status not in valid:
            status = "pending"
        steps.append({
            "id": str(raw.get("id") or idx + 1),
            "order": idx + 1,
            "name": str(raw.get("content") or raw.get("title") or f"Task {idx + 1}"),
            "tool_name": "todo",
            "params": {},
            "status": status,
        })

    return EventEnvelope(
        event="workflow_created" if first_workflow else "workflow_updated",
        timestamp=dt,
        data={
            "workflow_id": f"wf_{run_id}" if run_id else f"wf_{windagent_session_id}",
            "session_id": windagent_session_id,
            "objective": "",
            "status": "running",
            "steps": steps,
        },
    )
