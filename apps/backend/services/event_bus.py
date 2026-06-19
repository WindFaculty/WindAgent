"""In-memory pub/sub event bus for Phase 1 + Phase 2 persistence hook.

One bus per FastAPI app instance. Backed by asyncio.Queue per subscriber.
Phase 2 adds an optional publisher hook so we can mirror every event into
the `execution_events` table.

Reference: docs/event_protocol.md.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Optional

from schemas.event import EventEnvelope


log = logging.getLogger(__name__)

# Hook signature: async (session_id, envelope) -> None
PublisherHook = Callable[[str, EventEnvelope], Awaitable[None]]


class EventBus:
    """Session-scoped in-memory pub/sub.

    subscribe(session_id) returns an asyncio.Queue. publish(session_id, env)
    pushes a copy of the envelope to every active subscriber's queue.
    Drop policy: if a subscriber's queue is full, the event is dropped for
    that subscriber (slow consumer).
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._hooks: List[PublisherHook] = []

    # ---------- Publisher hook (Phase 2) ----------

    def add_publisher_hook(self, hook: PublisherHook) -> None:
        """Register an async hook fired after every publish (for DB write)."""
        self._hooks.append(hook)

    def clear_publisher_hooks(self) -> None:
        self._hooks.clear()

    # ---------- Core pub/sub ----------

    async def publish(self, session_id: str, envelope: EventEnvelope) -> int:
        """Deliver envelope to every subscriber of session_id. Returns count."""
        async with self._lock:
            queues = list(self._subscribers.get(session_id, []))
        delivered = 0
        for q in queues:
            try:
                q.put_nowait(envelope)
                delivered += 1
            except asyncio.QueueFull:
                # Slow subscriber. MVP policy: drop and continue.
                continue

        # Fire publisher hooks (DB mirror). Do not let one bad hook block others.
        if self._hooks:
            for hook in list(self._hooks):
                try:
                    await hook(session_id, envelope)
                except Exception:  # noqa: BLE001
                    log.exception("publisher hook %r failed", hook)

        return delivered

    async def subscribe(self, session_id: str, maxsize: int = 256) -> asyncio.Queue:
        """Register a new subscriber queue for session_id."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            self._subscribers.setdefault(session_id, []).append(q)
        return q

    async def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        """Remove a subscriber queue. Idempotent."""
        async with self._lock:
            queues = self._subscribers.get(session_id, [])
            if q in queues:
                queues.remove(q)
            if not queues:
                self._subscribers.pop(session_id, None)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, []))

    def active_sessions(self) -> List[str]:
        return list(self._subscribers.keys())


async def drain(queue: asyncio.Queue, timeout: float = 0.1) -> List[EventEnvelope]:
    """Test helper: drain all currently available events from a queue."""
    out: List[EventEnvelope] = []
    while True:
        try:
            out.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return out
