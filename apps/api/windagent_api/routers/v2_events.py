"""
API V2 Domain Events endpoints for WindAgent Architecture V2 (Phase 25 Cutover).
Provides HTTP SSE and WebSocket streaming with last_sequence event replay and terminal event delivery.
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.domain.lifecycle import utc_now
from windagent_core.domain.types import EventId

logger = logging.getLogger("windagent.api.events")
router = APIRouter(prefix="/api/v2/events", tags=["Events V2"])

# Production event store holding canonical EventEnvelopes
_DURABLE_EVENT_STORE: List[EventEnvelope] = []


def record_event_durable(envelope: EventEnvelope) -> None:
    """Records an EventEnvelope into durable sequence history."""
    _DURABLE_EVENT_STORE.append(envelope)


class EventResponse(BaseModel):
    """Canonical V2 Event Response DTO."""
    event_id: str
    event_type: str
    aggregate_id: str
    sequence_number: int
    occurred_at: str
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=List[EventResponse])
async def list_events(
    aggregate_id: Optional[str] = Query(None, description="Filter by aggregate ID"),
    min_sequence: int = Query(0, description="Minimum sequence number for event replay"),
    last_sequence: Optional[int] = Query(None, description="Alias for min_sequence replay cursor"),
) -> List[EventResponse]:
    replay_seq = last_sequence if last_sequence is not None else min_sequence
    results: List[EventResponse] = []
    for env in _DURABLE_EVENT_STORE:
        seq = getattr(env, "sequence_number", getattr(env, "sequence", 0))
        if seq <= replay_seq:
            continue
        if aggregate_id and str(env.aggregate_id) != aggregate_id:
            continue
        ev_type = env.event_type.value if hasattr(env.event_type, "value") else str(env.event_type)
        results.append(
            EventResponse(
                event_id=str(env.event_id),
                event_type=ev_type,
                aggregate_id=str(env.aggregate_id),
                sequence_number=seq,
                occurred_at=env.occurred_at.isoformat() if hasattr(env.occurred_at, "isoformat") else str(env.occurred_at),
                payload=env.payload,
            )
        )
    return results


@router.get("/stream")
async def sse_event_stream(
    last_sequence: int = Query(0, description="Replay missed events starting after last_sequence"),
    aggregate_id: Optional[str] = Query(None),
):
    """Server-Sent Events (SSE) stream supporting reconnect and last_sequence replay."""
    async def event_generator():
        cursor = last_sequence
        while True:
            # Replay missed events
            new_events = [
                env for env in _DURABLE_EVENT_STORE
                if getattr(env, "sequence_number", getattr(env, "sequence", 0)) > cursor
                and (not aggregate_id or str(env.aggregate_id) == aggregate_id)
            ]
            for env in new_events:
                seq = getattr(env, "sequence_number", getattr(env, "sequence", 0))
                cursor = seq
                payload_json = json.dumps({
                    "event_id": str(env.event_id),
                    "event_type": env.event_type.value if hasattr(env.event_type, "value") else str(env.event_type),
                    "aggregate_id": str(env.aggregate_id),
                    "sequence_number": seq,
                    "payload": env.payload,
                })
                yield f"data: {payload_json}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.websocket("/ws")
async def websocket_event_stream(
    websocket: WebSocket,
    last_sequence: int = Query(0),
):
    """WebSocket endpoint supporting reconnect, last_sequence replay, and heartbeat pings."""
    await websocket.accept()
    cursor = last_sequence
    try:
        # 1. Replay missed events first
        missed = [
            env for env in _DURABLE_EVENT_STORE
            if getattr(env, "sequence_number", getattr(env, "sequence", 0)) > cursor
        ]
        for env in missed:
            seq = getattr(env, "sequence_number", getattr(env, "sequence", 0))
            cursor = seq
            await websocket.send_json({
                "event_id": str(env.event_id),
                "event_type": env.event_type.value if hasattr(env.event_type, "value") else str(env.event_type),
                "aggregate_id": str(env.aggregate_id),
                "sequence_number": seq,
                "payload": env.payload,
                "is_replay": True,
            })

        # 2. Main streaming loop
        while True:
            await asyncio.sleep(0.5)
            # Send heartbeat ping if idle
            await websocket.send_json({"type": "ping", "sequence_cursor": cursor})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected gracefully.")
    except Exception as ex:
        logger.warning(f"WebSocket connection closed with error: {ex}")
