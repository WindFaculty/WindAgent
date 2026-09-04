"""In-process realtime fan-out with bounded replay for the debug vertical slice."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from windagent.kernel.events import EventEnvelope


@dataclass(frozen=True, slots=True)
class RealtimeMessage:
    """Monotonic process-local position plus its immutable envelope."""

    position: int
    event: EventEnvelope


class RealtimeSubscription:
    """One async consumer owned by a websocket or debug client."""

    def __init__(
        self,
        hub: RealtimeHub,
        queue: asyncio.Queue[RealtimeMessage],
    ) -> None:
        self._hub = hub
        self._queue = queue
        self._closed = False

    async def next(self, *, timeout_s: float | None = None) -> RealtimeMessage:
        if self._closed:
            raise RuntimeError("subscription is closed")
        if timeout_s is None:
            return await self._queue.get()
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        return await asyncio.wait_for(self._queue.get(), timeout=timeout_s)

    async def unsubscribe(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._hub._unsubscribe(self._queue)


class RealtimeHub:
    """Publish outbox-delivered events to live subscribers.

    Replay is deliberately bounded and process-local in Phase 7. The durable
    source remains ``platform_events``/``platform_outbox``; authenticated,
    durable reconnect replay belongs to the later realtime/API foundation.
    """

    def __init__(self, *, replay_capacity: int = 256, subscriber_capacity: int = 256) -> None:
        if replay_capacity < 1 or subscriber_capacity < 1:
            raise ValueError("replay and subscriber capacities must be at least 1")
        self._replay: deque[RealtimeMessage] = deque(maxlen=replay_capacity)
        self._subscriber_capacity = subscriber_capacity
        self._subscribers: set[asyncio.Queue[RealtimeMessage]] = set()
        self._position = 0
        self._lock = asyncio.Lock()

    async def publish(self, event: EventEnvelope) -> None:
        if not isinstance(event, EventEnvelope):
            raise TypeError("event must be an EventEnvelope")
        async with self._lock:
            self._position += 1
            message = RealtimeMessage(self._position, event)
            self._replay.append(message)
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            await queue.put(message)

    async def subscribe(self, *, after: int = 0) -> RealtimeSubscription:
        if after < 0:
            raise ValueError("after must be non-negative")
        queue: asyncio.Queue[RealtimeMessage] = asyncio.Queue(
            maxsize=self._subscriber_capacity
        )
        async with self._lock:
            replay = tuple(message for message in self._replay if message.position > after)
            if len(replay) > self._subscriber_capacity:
                replay = replay[-self._subscriber_capacity :]
            for message in replay:
                queue.put_nowait(message)
            self._subscribers.add(queue)
        return RealtimeSubscription(self, queue)

    async def _unsubscribe(self, queue: asyncio.Queue[RealtimeMessage]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)
