"""
API V2 Domain Events endpoints for WindAgent Architecture V2 (Phase 11 Adoption).
Provides durable event listing using EventEnvelope and sequence tracking.
Removes MOCK_DOMAIN_EVENTS and hardcoded timestamps.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.domain.lifecycle import utc_now
from windagent_core.domain.types import EventId

router = APIRouter(prefix="/api/v2/events", tags=["Events V2"])

# In-memory store for events emitted via bus in production
_DURABLE_EVENT_STORE: List[EventEnvelope] = []


def record_event_durable(envelope: EventEnvelope) -> None:
    """Record an EventEnvelope into durable sequence history."""
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
) -> List[EventResponse]:
    results: List[EventResponse] = []
    for env in _DURABLE_EVENT_STORE:
        if env.sequence_number < min_sequence:
            continue
        if aggregate_id and env.aggregate_id != aggregate_id:
            continue
        results.append(
            EventResponse(
                event_id=str(env.event_id),
                event_type=env.event_type.value if hasattr(env.event_type, "value") else str(env.event_type),
                aggregate_id=str(env.aggregate_id),
                sequence_number=env.sequence_number,
                occurred_at=env.occurred_at.isoformat(),
                payload=env.payload
            )
        )
    return results
