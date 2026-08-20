"""Conversation-scoped WebSocket stream backed by the canonical realtime hub (Phase 6).

Replay/live delivery is delegated to the composed ``RealtimeHub`` using
aggregate type ``conversation`` and the query ``after_sequence``.  This
endpoint never queries SQL or sleep-polls itself; if the composed hub is
unavailable it fails closed with WS 1011 rather than recreating the old
per-socket polling authority.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["Conversation streams"])


def _legacy_sender(websocket: WebSocket):
    """Render the stable conversation event envelope sent to every client.

    The compatibility endpoint keeps its legacy event-only wire shape: no
    leading control envelopes, and fields such as ``conversation_id``,
    ``data`` and ``is_replay`` are preserved for existing desktop/tests.
    """

    async def send(message: Dict[str, Any]) -> None:
        if message.get("type") in ("subscribed", "catchup_complete"):
            return
        metadata = message.get("metadata") or {}
        await websocket.send_json({
            "event_id": str(metadata.get("event_id") or message["event_id"]),
            "idempotency_key": str(
                metadata.get("idempotency_key") or message["event_id"]
            ),
            "conversation_id": str(message["aggregate_id"]),
            "agent_instance_id": metadata.get("agent_instance_id"),
            "agent_session_id": metadata.get("agent_session_id"),
            "sequence": int(message["sequence"]),
            "event_type": str(message["event_type"]),
            "data": dict(message.get("payload") or {}),
            "occurred_at": str(message["occurred_at"]),
            "is_replay": bool(message.get("is_replay", False)),
        })

    return send


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_event_stream(
    websocket: WebSocket,
    conversation_id: str,
    after_sequence: int = Query(0, ge=0),
) -> None:
    """Multiplex every agent's events on exactly one conversation socket.

    The database sequence is the cursor authority.  Reconnects therefore
    replay rows strictly after ``after_sequence`` without relying on any
    process-local WebSocket/event registry.
    """
    await websocket.accept()
    container = getattr(websocket.app.state, "container", None)
    hub = getattr(container, "realtime_hub", None) if container is not None else None
    if hub is None:
        await websocket.close(code=1011, reason="realtime hub unavailable")
        return
    telemetry = getattr(container, "release_telemetry", None)
    if after_sequence > 0 and telemetry is not None:
        telemetry.record_websocket_reconnect()

    connection_id = f"conn_{uuid.uuid4().hex[:12]}"
    subscription_id: str | None = None
    try:
        subscription_id = await hub.subscribe(
            aggregate_type="conversation",
            aggregate_id=conversation_id,
            after_sequence=after_sequence,
            sender=_legacy_sender(websocket),
            connection_id=connection_id,
        )
        while True:
            raw = await websocket.receive_text()
            if raw == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json({
                    "type": "error",
                    "error": "invalid_json",
                    "message": "message must be valid JSON",
                })
                continue
            msg_type = message.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "unsubscribe":
                await hub.unsubscribe(subscription_id)
                subscription_id = None
                await websocket.send_json({"type": "unsubscribed"})
                break
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": "unsupported_message",
                    "message": f"unsupported message type: {msg_type!r}",
                })
    except WebSocketDisconnect:
        return
    finally:
        if subscription_id is not None:
            try:
                await hub.unsubscribe(subscription_id)
            except Exception:
                pass
        try:
            await hub.disconnect(connection_id)
        except Exception:
            pass