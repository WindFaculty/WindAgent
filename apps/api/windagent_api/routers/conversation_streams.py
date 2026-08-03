"""Conversation-scoped WebSocket stream backed by durable event replay."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


router = APIRouter(tags=["Conversation streams"])


def _envelope(row: dict[str, Any], *, is_replay: bool) -> dict[str, Any]:
    """Render the stable conversation event envelope sent to every client."""
    return {
        "event_id": str(row["event_id"]),
        "idempotency_key": str(row.get("idempotency_key") or row["event_id"]),
        "conversation_id": str(row["conversation_id"]),
        "agent_instance_id": row.get("agent_instance_id"),
        "agent_session_id": row.get("agent_session_id"),
        "sequence": int(row["sequence"]),
        "event_type": str(row["event_type"]),
        "data": dict(row.get("data") or {}),
        "occurred_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else str(row["created_at"]),
        "is_replay": is_replay,
    }


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
    database = getattr(container, "db", None)
    if database is None:
        await websocket.close(code=1011, reason="conversation event store unavailable")
        return
    telemetry = getattr(container, "release_telemetry", None)
    if after_sequence > 0 and telemetry is not None:
        telemetry.record_websocket_reconnect()

    cursor = after_sequence
    replaying = True
    try:
        while True:
            async with database.session_factory() as session:
                rows = await MultiAgentRepository(session).conversation_events_after(
                    conversation_id, cursor
                )
            for row in rows:
                cursor = int(row["sequence"])
                await websocket.send_json(_envelope(row, is_replay=replaying))
            replaying = False
            if not rows:
                # Keepalive carries the authoritative cursor but is deliberately
                # not an event, so clients never merge it into agent timelines.
                await websocket.send_json({"type": "ping", "sequence": cursor})
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
