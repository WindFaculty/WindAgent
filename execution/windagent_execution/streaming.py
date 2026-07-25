"""
Streaming Execution Progress & Logs for WindAgent Execution V2 (Phase 18).
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class StreamChunk:
    step_run_id: str
    chunk_type: str  # log | stdout | stderr | metric | progress
    content: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionStreamManager:
    """Publishes and listens to real-time execution stream chunks."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue[StreamChunk]]] = {}

    def subscribe(self, step_run_id: str) -> asyncio.Queue[StreamChunk]:
        queue: asyncio.Queue[StreamChunk] = asyncio.Queue()
        if step_run_id not in self._queues:
            self._queues[step_run_id] = []
        self._queues[step_run_id].append(queue)
        return queue

    def unsubscribe(self, step_run_id: str, queue: asyncio.Queue[StreamChunk]) -> None:
        if step_run_id in self._queues:
            self._queues[step_run_id] = [q for q in self._queues[step_run_id] if q is not queue]

    async def emit_chunk(self, chunk: StreamChunk) -> None:
        listeners = self._queues.get(chunk.step_run_id, [])
        for q in listeners:
            await q.put(chunk)
