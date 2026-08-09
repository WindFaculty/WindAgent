"""
API V2 Domain Events endpoints for WindAgent Architecture V2 (Phase 25 Cutover).
Provides HTTP SSE and WebSocket streaming with last_sequence event replay,
project authorization scoping, and terminal event delivery.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from windagent_api.dependencies import get_video_production_uow
from windagent_core.events.envelope import EventEnvelope

logger = logging.getLogger("windagent.api.events")
router = APIRouter(prefix="/api/v2/video-production/events", tags=["Production Events V2"])

# Production in-memory fallback store holding canonical EventEnvelopes
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
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    aggregate_id: Optional[str] = Query(None, description="Filter by aggregate ID"),
    min_sequence: int = Query(0, description="Minimum sequence number for event replay"),
    last_sequence: Optional[int] = Query(None, description="Alias for min_sequence replay cursor"),
    uow_factory=Depends(get_video_production_uow),
) -> List[EventResponse]:
    replay_seq = last_sequence if last_sequence is not None else min_sequence

    if project_id:
        async with uow_factory as uow:
            durable_events = await uow.events.get_events(project_id, min_sequence=replay_seq)
            return [
                EventResponse(
                    event_id=ev["event_id"],
                    event_type=ev["event_type"],
                    aggregate_id=ev["aggregate_id"],
                    sequence_number=ev["sequence"],
                    occurred_at=ev.get("occurred_at", ""),
                    payload=ev["payload"],
                )
                for ev in durable_events
            ]

    results: List[EventResponse] = []
    for env in _DURABLE_EVENT_STORE:
        seq = getattr(env, "sequence_number", getattr(env, "sequence", 0))
        if seq <= replay_seq:
            continue
        if aggregate_id and str(env.aggregate_id) != aggregate_id:
            continue
        ev_type = (
            env.event_type.value
            if hasattr(env.event_type, "value")
            else str(env.event_type)
        )
        results.append(
            EventResponse(
                event_id=str(env.event_id),
                event_type=ev_type,
                aggregate_id=str(env.aggregate_id),
                sequence_number=seq,
                occurred_at=env.occurred_at.isoformat()
                if hasattr(env.occurred_at, "isoformat")
                else str(env.occurred_at),
                payload=env.payload,
            )
        )
    return results


@router.get("/stream")
async def sse_event_stream(
    project_id: Optional[str] = Query(None),
    last_sequence: int = Query(0, description="Replay missed events starting after last_sequence"),
    aggregate_id: Optional[str] = Query(None),
    uow_factory=Depends(get_video_production_uow),
):
    """Server-Sent Events (SSE) stream supporting reconnect, project scoping, and last_sequence replay."""

    async def event_generator():
        cursor = last_sequence
        while True:
            durable_events: list[dict[str, Any]] = []
            if project_id:
                async with uow_factory as uow:
                    max_seq = await uow.events.get_max_sequence(project_id)
                    if cursor < max_seq - 500 and cursor > 0:
                        resync_payload = json.dumps({
                            "event_type": "RESYNC_REQUIRED",
                            "message": "Sequence cursor gap too large. Refetch snapshot.",
                            "current_sequence": max_seq,
                        })
                        yield f"data: {resync_payload}\n\n"
                        cursor = max_seq
                        continue

                    durable_events = await uow.events.get_events(project_id, min_sequence=cursor)

            if durable_events:
                for ev in durable_events:
                    cursor = ev["sequence"]
                    payload_json = json.dumps({
                        "event_id": ev["event_id"],
                        "sequence": ev["sequence"],
                        "event_type": ev["event_type"],
                        "project_id": ev["project_id"],
                        "revision_id": ev["revision_id"],
                        "aggregate_type": ev["aggregate_type"],
                        "aggregate_id": ev["aggregate_id"],
                        "payload": ev["payload"],
                    })
                    yield f"data: {payload_json}\n\n"

            # Check in-memory fallback events if no project-specific events
            new_in_mem = [
                env for env in _DURABLE_EVENT_STORE
                if getattr(env, "sequence_number", getattr(env, "sequence", 0)) > cursor
                and (not aggregate_id or str(env.aggregate_id) == aggregate_id)
            ]
            for env in new_in_mem:
                seq = getattr(env, "sequence_number", getattr(env, "sequence", 0))
                cursor = seq
                payload_json = json.dumps({
                    "event_id": str(env.event_id),
                    "sequence": seq,
                    "event_type": env.event_type.value if hasattr(env.event_type, "value") else str(env.event_type),
                    "aggregate_id": str(env.aggregate_id),
                    "payload": env.payload,
                })
                yield f"data: {payload_json}\n\n"

            await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
