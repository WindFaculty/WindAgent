"""
API V2 Domain Events endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/events", tags=["Events V2"])

MOCK_DOMAIN_EVENTS = [
    {
        "event_id": "evt_01",
        "event_type": "TaskCreatedDomainEvent",
        "aggregate_id": "task_demo",
        "payload": {"prompt": "Fix calculation"},
        "timestamp": "2026-07-23T19:00:00Z"
    },
    {
        "event_id": "evt_02",
        "event_type": "WorkflowStartedDomainEvent",
        "aggregate_id": "task_demo",
        "payload": {"workflow_name": "bugfix"},
        "timestamp": "2026-07-23T19:00:01Z"
    }
]


class EventResponse(BaseModel):
    event_id: str
    event_type: str
    aggregate_id: str
    payload: Dict[str, Any]
    timestamp: str


@router.get("", response_model=List[EventResponse])
async def list_events(aggregate_id: Optional[str] = None) -> List[EventResponse]:
    if aggregate_id:
        filtered = [e for e in MOCK_DOMAIN_EVENTS if e["aggregate_id"] == aggregate_id]
        return [EventResponse(**e) for e in filtered]
    return [EventResponse(**e) for e in MOCK_DOMAIN_EVENTS]
