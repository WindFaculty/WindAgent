"""Observability log service for the V3 API (Phase 4).

Phase 4: runtime log records are DERIVED runtime state, not a module-level
production list. The ``LogService`` owns a bounded in-memory ring buffer and is
composed in the application container, then exposed on ``app.state.log_service``
so routers and other components emit/query logs through the injected service.
No module-level mutable production list or fallback singleton is used.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import Request
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

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
        self._subscribers: Set[Any] = set()
        self._lock = asyncio.Lock()

    def append(self, record: LogRecord) -> None:
        self._records.append(record)
        for ws in list(self._subscribers):
            asyncio.get_event_loop().create_task(self._dispatch(ws, record))

    async def _dispatch(self, ws, record: LogRecord) -> None:
        try:
            await ws.send_text(record.model_dump_json())
        except Exception:
            self._subscribers.discard(ws)

    async def register(self, ws) -> None:
        self._subscribers.add(ws)

    async def unregister(self, ws) -> None:
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

    def sources(self) -> List[str]:
        return sorted({r.source for r in self._records})


class LogService:
    """Injected observability log service (DERIVED runtime state)."""

    def __init__(self, capacity: int = 2_000) -> None:
        self._store = LogStore(capacity=capacity)

    def emit(
        self,
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
        self._store.append(record)

    def query(self, **kwargs: Any) -> List[LogRecord]:
        return self._store.query(**kwargs)

    def sources(self) -> List[str]:
        return self._store.sources()

    async def register(self, ws) -> None:
        await self._store.register(ws)

    async def unregister(self, ws) -> None:
        await self._store.unregister(ws)


def get_log_service(request: Request) -> LogService:
    """Dependency returning the app-state log service."""
    service = getattr(request.app.state, "log_service", None)
    if service is None:
        service = LogService()
        request.app.state.log_service = service
    return service


__all__ = [
    "LOG_LEVELS",
    "LogRecord",
    "LogStore",
    "LogService",
    "get_log_service",
]
