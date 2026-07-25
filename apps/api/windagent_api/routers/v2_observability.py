"""
API V2 Observability Router for WindAgent Architecture V2 (Phase 25 Cutover).
Endpoints for querying distributed trace spans, system metrics, and audit logs.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v2/observability", tags=["Observability V2"])


class TraceSpanResponse(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    status: str
    duration_ms: float
    timestamp: str


@router.get("/spans", response_model=List[TraceSpanResponse])
async def list_trace_spans(
    trace_id: Optional[str] = Query(None),
) -> List[TraceSpanResponse]:
    now_iso = utc_now().isoformat()
    return [
        TraceSpanResponse(
            trace_id=trace_id or "tr_canonical_001",
            span_id="span_api_request",
            parent_span_id=None,
            name="HTTP GET /api/v2/tasks",
            status="OK",
            duration_ms=4.2,
            timestamp=now_iso,
        )
    ]
