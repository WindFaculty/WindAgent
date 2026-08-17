"""
V3 Logs Router — Canonical Log Authority (Phase 13D).

LogRecord is a structured, filterable runtime log entry with correlation_id /
trace_id. Records are produced by real runtime activity (API requests, agent
events, task transitions, memory writes) — no static fixtures. A bounded
in-memory ring buffer holds recent records; /ws/v3/logs streams new records as
they are produced.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v3/logs", tags=["Logs V3"])
ws_router = APIRouter(prefix="/ws/v3/logs", tags=["Logs V3 Realtime"])

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class LogRecord(BaseModel):
    timestamp: str
    level: str
    source: str
    message: str
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_instance_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LogStore:
    """Bounded in-memory log ring buffer with realtime subscriber fan-out."""

    def __init__(self, capacity: int = 2_000) -> None:
        self._records: Deque[LogRecord] = deque(maxlen=capacity)
        self._subscribers: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    def append(self, record: LogRecord) -> None:
        self._records.append(record)
        for ws in list(self._subscribers):
            asyncio.get_event_loop().create_task(self._dispatch(ws, record))

    async def _dispatch(self, ws: WebSocket, record: LogRecord) -> None:
        try:
            await ws.send_text(record.model_dump_json())
        except Exception:
            self._subscribers.discard(ws)

    async def register(self, ws: WebSocket) -> None:
        self._subscribers.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        self._subscribers.discard(ws)

    def query(
        self,
        level: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[LogRecord]:
        records = list(self._records)
        if level:
            records = [r for r in records if r.level == level.upper()]
        if source:
            records = [r for r in records if source.lower() in r.source.lower()]
        if correlation_id:
            records = [r for r in records if r.correlation_id == correlation_id]
        if conversation_id:
            records = [r for r in records if r.conversation_id == conversation_id]
        if agent_instance_id:
            records = [r for r in records if r.agent_instance_id == agent_instance_id]
        if task_id:
            records = [r for r in records if r.task_id == task_id]
        records.reverse()
        return records[:limit]


def get_log_store() -> LogStore:
    return LogStore()


_log_store: Optional[LogStore] = None
_api_logs: List[LogRecord] = []


def emit_log(
    level: str,
    source: str,
    message: str,
    *,
    correlation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    agent_instance_id: Optional[str] = None,
    task_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Module-level sink so any runtime component can emit a real log record."""
    global _log_store
    if _log_store is None:
        _log_store = LogStore()
    from windagent_core.domain.lifecycle import utc_now

    record = LogRecord(
        timestamp=utc_now().isoformat(),
        level=level,
        source=source,
        message=message,
        correlation_id=correlation_id,
        trace_id=trace_id,
        conversation_id=conversation_id,
        agent_instance_id=agent_instance_id,
        task_id=task_id,
        metadata=metadata or {},
    )
    _api_logs.append(record)
    _log_store.append(record)


def current_logs(limit: int = 500) -> List[LogRecord]:
    if _log_store is None:
        return []
    return _log_store.query(limit=limit)


@router.get("", response_model=List[LogRecord], operation_id="logs.list")
async def list_logs(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    agent_instance_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1_000),
) -> List[LogRecord]:
    """List runtime log records with filters. Real activity only."""
    if _log_store is None:
        return []
    return _log_store.query(
        level=level,
        source=source,
        correlation_id=correlation_id,
        conversation_id=conversation_id,
        agent_instance_id=agent_instance_id,
        task_id=task_id,
        limit=limit,
    )


@router.get("/sources", response_model=List[str], operation_id="logs.sources")
async def list_log_sources() -> List[str]:
    """Distinct sources present in the current runtime log buffer."""
    if _log_store is None:
        return []
    sources = sorted({r.source for r in _log_store._records})
    return sources


@ws_router.websocket("")
async def logs_realtime_ws(websocket: WebSocket):
    """Stream real log records as they are produced at runtime."""
    await websocket.accept()
    store = _log_store or LogStore()
    await store.register(websocket)
    try:
        await websocket.send_text(json.dumps({"event": "log.stream.ready"}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await store.unregister(websocket)