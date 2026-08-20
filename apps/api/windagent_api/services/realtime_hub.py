"""Canonical API realtime hub service (Phase 6).

The hub owns subscription state, exact stream cursors, duplicate suppression,
per-subscription ordering locks, live ``publish`` delivery wired to the
``EventDispatcher`` wildcard, and one explicit read-only SQL fallback loop for
cross-process catch-up.  It never claims or mutates outbox rows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from windagent_core.contracts.realtime import RealtimeReplayPort
from windagent_core.events.envelope import EventEnvelope

logger = logging.getLogger("windagent.api.realtime_hub")

Sender = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class Subscription:
    """One aggregate stream subscription with its own cursor and ordering lock."""

    subscription_id: str
    connection_id: str
    aggregate_type: str
    aggregate_id: str
    cursor: int
    sender: Sender
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    replay_complete: bool = False


class RealtimeHub:
    """In-process live delivery hub with durable SQL replay and fallback catch-up.

    Lifecycle: call ``start()`` once (spawns the fallback loop) and ``stop()``
    before database shutdown.  No tasks leak: ``stop()`` cancels the single
    fallback task.
    """

    def __init__(
        self,
        replay: RealtimeReplayPort,
        *,
        fallback_interval_seconds: float = 1.0,
        replay_page_size: int = 500,
    ) -> None:
        self._replay = replay
        self._relay_interval = fallback_interval_seconds
        self._replay_page_size = replay_page_size
        self._subscriptions: Dict[str, Subscription] = {}
        self._by_connection: Dict[str, Set[str]] = defaultdict(set)
        self._registry_lock = asyncio.Lock()
        self._running = False
        self._relay_task: Optional[asyncio.Task] = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    @property
    def active_subscription_count(self) -> int:
        """Number of currently registered subscriptions (test/introspection)."""
        return len(self._subscriptions)

    async def start(self) -> None:
        """Start the single read-only SQL fallback loop."""
        if self._running:
            return
        self._running = True
        self._relay_task = asyncio.create_task(self._relay_loop())
        logger.info("RealtimeHub started.")

    async def stop(self) -> None:
        """Stop the fallback loop and clear all subscriptions."""
        self._running = False
        if self._relay_task is not None:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass
            self._relay_task = None
        async with self._registry_lock:
            self._subscriptions.clear()
            self._by_connection.clear()
        logger.info("RealtimeHub stopped.")

    # ── subscription management ────────────────────────────────────────────

    async def subscribe(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        after_sequence: int,
        sender: Sender,
        connection_id: str,
    ) -> str:
        """Register a subscription, run initial SQL catch-up, then live push.

        A repeated subscribe for the same aggregate stream on the same
        connection replaces the previous subscription instead of creating a
        duplicate delivery path.  Returns the subscription id.  Control
        messages ``subscribed`` and ``catchup_complete`` are delivered through
        the same sender.
        """
        subscription_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub = Subscription(
            subscription_id=subscription_id,
            connection_id=connection_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            cursor=after_sequence,
            sender=sender,
        )
        async with self._registry_lock:
            existing = self._find_subscription(
                connection_id, aggregate_type, aggregate_id
            )
            if existing is not None:
                self._subscriptions.pop(existing.subscription_id, None)
                conn_subs = self._by_connection.get(connection_id)
                if conn_subs is not None:
                    conn_subs.discard(existing.subscription_id)
            self._subscriptions[subscription_id] = sub
            self._by_connection[connection_id].add(subscription_id)
        try:
            await sender(
                {
                    "type": "subscribed",
                    "subscription_id": subscription_id,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "cursor": after_sequence,
                }
            )
            # Send catchup_complete while still holding the per-subscription
            # lock and only then mark replay complete, so a publisher/fallback
            # waiting on that lock can never deliver a live event before the
            # client observes the replay -> catch-up complete -> live ordering.
            async with sub.lock:
                final_cursor = await self._drain_replay(sub)
                await sender(
                    {
                        "type": "catchup_complete",
                        "subscription_id": subscription_id,
                        "cursor": final_cursor,
                    }
                )
                sub.replay_complete = True
        except Exception:
            await self.unsubscribe(subscription_id)
            raise
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove one subscription and its connection bookkeeping."""
        async with self._registry_lock:
            sub = self._subscriptions.pop(subscription_id, None)
            if sub is None:
                return
            conn_subs = self._by_connection.get(sub.connection_id)
            if conn_subs is not None:
                conn_subs.discard(subscription_id)
                if not conn_subs:
                    self._by_connection.pop(sub.connection_id, None)

    async def unsubscribe_stream(
        self,
        *,
        connection_id: str,
        aggregate_type: str,
        aggregate_id: str,
    ) -> Optional[str]:
        """Unsubscribe the stream subscription owned by a connection.

        The frontend client identifies subscriptions by aggregate stream
        identity (``aggregate_type`` + ``aggregate_id``) rather than by
        ``subscription_id``.  Returns the removed subscription id, or ``None``
        when no such subscription exists on this connection.
        """
        async with self._registry_lock:
            sub = self._find_subscription(
                connection_id, aggregate_type, aggregate_id
            )
            if sub is None:
                return None
            self._subscriptions.pop(sub.subscription_id, None)
            conn_subs = self._by_connection.get(connection_id)
            if conn_subs is not None:
                conn_subs.discard(sub.subscription_id)
                if not conn_subs:
                    self._by_connection.pop(connection_id, None)
            return sub.subscription_id

    async def disconnect(self, connection_id: str) -> None:
        """Unregister every subscription owned by a connection."""
        async with self._registry_lock:
            sub_ids = list(self._by_connection.pop(connection_id, set()))
        for sub_id in sub_ids:
            await self.unsubscribe(sub_id)

    def _find_subscription(
        self,
        connection_id: str,
        aggregate_type: str,
        aggregate_id: str,
    ) -> Optional[Subscription]:
        """Return the subscription for a stream on a connection (registry lock held)."""
        for sub_id in self._by_connection.get(connection_id, ()):
            sub = self._subscriptions.get(sub_id)
            if (
                sub is not None
                and sub.aggregate_type == aggregate_type
                and sub.aggregate_id == aggregate_id
            ):
                return sub
        return None

    # ── delivery ───────────────────────────────────────────────────────────

    async def publish(self, envelope: EventEnvelope) -> None:
        """Live in-process delivery to matching subscriptions (dispatcher wildcard).

        Under each subscription lock, durable replay is drained first so a
        slower-committed lower sequence is never skipped by a faster live
        envelope.  The dispatcher envelope itself is sent only if it was not
        returned by replay and is still newer than the cursor.
        """
        if not envelope.aggregate_type or not envelope.aggregate_id:
            return
        async with self._registry_lock:
            subs = list(self._subscriptions.values())
        for sub in subs:
            if (
                sub.aggregate_type != envelope.aggregate_type
                or sub.aggregate_id != envelope.aggregate_id
            ):
                continue
            async with sub.lock:
                if not sub.replay_complete:
                    # Initial catch-up still owns the lock and drains every
                    # committed event, so nothing is lost by skipping here.
                    continue
                try:
                    await self._drain_replay(sub)
                except Exception as exc:
                    logger.warning(
                        "RealtimeHub publish replay drain failed for %s: %s",
                        sub.subscription_id,
                        exc,
                    )
                    continue
                if envelope.sequence <= sub.cursor:
                    continue  # already delivered by replay (or duplicate)
                try:
                    await sub.sender(self._event_message(envelope, is_replay=False))
                except Exception as exc:
                    logger.warning(
                        "RealtimeHub publish send failed for %s: %s",
                        sub.subscription_id,
                        exc,
                    )
                    continue
                sub.cursor = envelope.sequence

    async def _catch_up(self, sub: Subscription) -> int:
        """Initial SQL catch-up with pagination, strictly ascending, deduped."""
        async with sub.lock:
            return await self._drain_replay(sub)

    async def _drain_replay(self, sub: Subscription) -> int:
        """Deliver durable events strictly after the cursor, ascending, paginated.

        Must be called while holding ``sub.lock``.  Sender errors propagate to
        the caller so initial catch-up can fail the subscription.  Returns the
        final cursor.
        """
        while True:
            events = await self._replay.events_after(
                sub.aggregate_type,
                sub.aggregate_id,
                sub.cursor,
                self._replay_page_size,
            )
            if not events:
                break
            advanced = False
            for env in events:
                if env.sequence <= sub.cursor:
                    continue
                await sub.sender(self._event_message(env, is_replay=True))
                sub.cursor = env.sequence
                advanced = True
            if not advanced or len(events) < self._replay_page_size:
                break
        return sub.cursor

    # ── cross-process fallback ─────────────────────────────────────────────

    async def _relay_loop(self) -> None:
        """One read-only SQL relay, active only while subscriptions exist."""
        while self._running:
            try:
                await self._relay_catch_up()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("RealtimeHub fallback catch-up error: %s", exc)
            try:
                await asyncio.sleep(self._relay_interval)
            except asyncio.CancelledError:
                break

    async def _relay_catch_up(self) -> None:
        async with self._registry_lock:
            subs = list(self._subscriptions.values())
        if not subs:
            return
        for sub in subs:
            async with sub.lock:
                if not sub.replay_complete:
                    continue
                try:
                    await self._drain_replay(sub)
                except Exception as exc:
                    logger.warning(
                        "RealtimeHub fallback replay error for %s: %s",
                        sub.subscription_id,
                        exc,
                    )

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _event_message(envelope: EventEnvelope, *, is_replay: bool) -> Dict[str, Any]:
        """Canonical event message plus internal routing metadata.

        The wire event_id preserves the durable row id (opaque ids are kept in
        envelope metadata by the replay adapter).  The canonical root endpoint
        strips the internal ``metadata``/``is_replay`` keys before sending.
        """
        metadata = dict(envelope.metadata or {})
        return {
            "event_id": str(metadata.get("event_id") or envelope.event_id),
            "event_type": envelope.event_type,
            "aggregate_type": envelope.aggregate_type,
            "aggregate_id": envelope.aggregate_id,
            "sequence": envelope.sequence,
            "occurred_at": (
                envelope.occurred_at.isoformat()
                if hasattr(envelope.occurred_at, "isoformat")
                else str(envelope.occurred_at)
            ),
            "payload": dict(envelope.payload or {}),
            "metadata": metadata,
            "is_replay": is_replay,
        }


__all__ = ["RealtimeHub", "Subscription"]