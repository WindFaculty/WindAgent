"""Recording-take & timeline-event routers (/api/v3/live-record/takes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from windagent_api.routers.v3.live_record.dependencies import (
    get_live_record_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.live_record.schemas import (
    AppendEventRequest,
    EventListResponse,
)
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)

router = APIRouter(prefix="/live-record/takes", tags=["live-record"])


class RecordSegmentRequest(BaseModel):
    """One finalized MKV segment relayed from the desktop engine host."""

    segment_id: Optional[str] = Field(default=None)
    segment_index: int = Field(ge=0)
    file_token: str = ""
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_sec: Optional[float] = Field(default=None, ge=0)
    is_playable: bool = False
    manifest: Dict[str, Any] = Field(default_factory=dict)


@router.get("/{take_id}")
async def get_take(
    take_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.get_take(take_id)


@router.get("/{take_id}/events", response_model=EventListResponse)
async def list_take_events(
    take_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> EventListResponse:
    """Append-only recording timeline ordered by per-take ``seq``."""
    items = await service.list_take_events(take_id)
    return EventListResponse(items=items)


@router.post("/{take_id}/events", status_code=201)
async def append_take_event(
    take_id: str = Path(..., min_length=1),
    body: AppendEventRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Append one timeline row (CUE_ENTERED / ACTION_EXECUTED / MARKER / ...);
    the repository assigns the monotonic per-take sequence."""
    return await service.append_take_event(
        take_id_raw=take_id,
        payload=body.model_dump(),
        idempotency_key=idempotency_key,
    )


@router.post("/{take_id}/segments", status_code=201)
async def record_take_segment(
    take_id: str = Path(..., min_length=1),
    body: RecordSegmentRequest = ...,
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Ingest one finalized MKV segment (engine → host → DB lineage, LR_P8).

    Upsert keyed by segment_id — replays after a host reconnect are
    idempotent; no idempotency-key requirement because the natural key already
    collapses duplicates.
    """
    return await service.record_take_segment(
        take_id_raw=take_id,
        payload=body.model_dump(mode="json"),
    )


@router.get("/{take_id}/segments")
async def list_take_segments(
    take_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    items = await service.list_take_segments(take_id)
    return {"items": items}
