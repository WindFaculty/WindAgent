"""WebSocket router: per-session event stream + client control messages.

URL: /ws/{session_id}

Server -> Client (one JSON frame per event):
    { "event": str, "timestamp": ISO 8601, "data": {...} }
See docs/event_protocol.md.

Client -> Server (control messages, JSON text frame):
    { "action": "pause"  }
    { "action": "resume" }
    { "action": "stop"   }

The server replies with the corresponding `user_paused` / `user_resumed` /
`user_stopped` event on the bus so all subscribers see it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from schemas.event import EventEnvelope, UserControlData
from services.event_bus import EventBus
from services.permission_service import PermissionService
from services.workflow_runner import WorkflowRunner


logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# Mapping action -> (runner method, event_name to echo).
_ACTION_MAP: Dict[str, tuple[str, str]] = {
    "pause": ("pause", "user_paused"),
    "resume": ("resume", "user_resumed"),
    "stop": ("stop", "user_stopped"),
}


# Permission actions are different: they go through PermissionService
# instead of WorkflowRunner. Map action -> (kind, grant).
_PERMISSION_ACTIONS = {
    "permission_granted",
    "permission_denied",
}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: UUID) -> None:
    bus: EventBus = websocket.app.state.event_bus
    sessions = websocket.app.state.session_service
    runner: WorkflowRunner = websocket.app.state.workflow_runner
    permissions = websocket.app.state.permission_service
    sid = str(session_id)

    # Validate session exists before accepting.
    chat = await sessions.get_session(session_id)
    if chat is None:
        await websocket.close(code=4404, reason="session not found")
        return

    await websocket.accept()
    queue = await bus.subscribe(sid)
    logger.info("ws accepted session=%s subscribers=%d", sid, bus.subscriber_count(sid))

    reader_task = asyncio.create_task(
        _read_control_messages(websocket, runner, permissions, bus, sid),
        name=f"ws-reader-{sid}",
    )

    try:
        while True:
            try:
                envelope = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                # Keepalive — clients should ignore this.
                try:
                    await websocket.send_text("ping")
                except Exception:  # noqa: BLE001
                    break
                continue
            except asyncio.CancelledError:
                break

            try:
                await websocket.send_json(envelope.model_dump(mode="json"))
            except Exception:  # noqa: BLE001
                break
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("websocket error for session %s", sid)
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await bus.unsubscribe(sid, queue)
        logger.info("ws closed session=%s", sid)


async def _read_control_messages(
    websocket: WebSocket,
    runner: WorkflowRunner,
    permissions: "PermissionService",
    bus: EventBus,
    session_id: str,
) -> None:
    """Read client text frames and dispatch pause/resume/stop actions
    AND permission decisions."""
    sid_uuid = UUID(session_id)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                # Silently ignore garbage frames (keepalive pings, etc).
                continue

            action = payload.get("action") if isinstance(payload, dict) else None

            # ----- permission decision (Phase 7) -----
            if action in _PERMISSION_ACTIONS:
                request_id_raw = payload.get("request_id") if isinstance(payload, dict) else None
                if not request_id_raw:
                    continue
                try:
                    request_id = UUID(str(request_id_raw))
                except (TypeError, ValueError):
                    continue
                granted = action == "permission_granted"
                try:
                    await permissions.resolve_permission(
                        request_id, granted=granted
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "ws control: resolve_permission failed for %s",
                        request_id,
                    )
                continue

            # ----- runner control (Phase 5) -----
            mapping = _ACTION_MAP.get(action or "")
            if mapping is None:
                # Unknown action — skip.
                continue

            method_name, event_name = mapping
            method = getattr(runner, method_name, None)
            if method is None:
                continue
            try:
                ok = method(sid_uuid)
            except Exception:  # noqa: BLE001
                logger.exception("ws control: runner.%s failed", method_name)
                continue

            if not ok:
                continue

            # Echo the user_* event on the bus so other subscribers also see it.
            state = runner.get_state(sid_uuid)
            workflow_id: Optional[UUID] = None
            if state and state.get("workflow_id"):
                try:
                    workflow_id = UUID(state["workflow_id"])
                except (TypeError, ValueError):
                    workflow_id = None
            env = EventEnvelope(
                event=event_name,
                data=UserControlData(
                    session_id=sid_uuid,
                    workflow_id=workflow_id,
                ).model_dump(mode="json"),
            )
            await bus.publish(session_id, env)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        logger.exception("ws control reader crashed for session %s", session_id)