"""
V3 Logs Router — Canonical Log Authority (Phase 13D).

LogRecord is a structured, filterable runtime log entry with correlation_id /
trace_id. Records are produced by real runtime activity (API requests, agent
events, task transitions, memory writes) — no static fixtures. A bounded
in-memory ring buffer holds recent records; /ws/v3/logs streams new records as
they are produced.

Phase 4: the log buffer is DERIVED runtime state owned by the injected
``LogService`` (composed in the container and exposed on ``app.state``), not a
module-level production list.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from windagent_api.services.log_service import (
    LogRecord,
    LogService,
    get_log_service,
)

router = APIRouter(prefix="/api/v3/logs", tags=["Logs V3"])
ws_router = APIRouter(prefix="/ws/v3/logs", tags=["Logs V3 Realtime"])


@router.get("", response_model=list[LogRecord], operation_id="logs.list")
async def list_logs(
    level: str | None = Query(None),
    source: str | None = Query(None),
    correlation_id: str | None = Query(None),
    conversation_id: str | None = Query(None),
    agent_instance_id: str | None = Query(None),
    task_id: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1_000),
    service: LogService = Depends(get_log_service),
) -> list[LogRecord]:
    """List runtime log records with filters. Real activity only."""
    return service.query(
        level=level,
        source=source,
        correlation_id=correlation_id,
        conversation_id=conversation_id,
        agent_instance_id=agent_instance_id,
        task_id=task_id,
        limit=limit,
    )


@router.get("/sources", response_model=list[str], operation_id="logs.sources")
async def list_log_sources(
    service: LogService = Depends(get_log_service),
) -> list[str]:
    """Distinct sources present in the current runtime log buffer."""
    return service.sources()


@ws_router.websocket("")
async def logs_realtime_ws(websocket: WebSocket):
    """Stream real log records as they are produced at runtime."""
    await websocket.accept()
    service = getattr(websocket.app.state, "log_service", None)
    if service is None:
        service = LogService()
        websocket.app.state.log_service = service
    await service.register(websocket)
    try:
        await websocket.send_text(json.dumps({"event": "log.stream.ready"}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await service.unregister(websocket)
