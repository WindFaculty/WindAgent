"""Outbox publisher: the claim → deliver → finalize drain loop.

Preserved semantics from the old transactional outbox processor: only
claimed records are delivered, failures increment the attempt counter with
exponential-free fixed backoff until ``max_attempts`` moves the record to
``dead_letter``, and delivery itself never runs inside a database
transaction.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

from windagent.kernel.time import Clock, SystemClock

from .contracts import EventPublisher
from .outbox import (
    DEFAULT_BACKOFF_S,
    DEFAULT_LEASE_S,
    DEFAULT_MAX_ATTEMPTS,
    OutboxRecord,
    OutboxStore,
)

type DeadLetterHook = Callable[[OutboxRecord], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class PublishReport:
    """Outcome of one publisher drain cycle."""

    claimed: int
    published: int
    retried: int
    dead_lettered: int

    @property
    def idle(self) -> bool:
        """Whether the cycle had nothing to deliver."""
        return self.claimed == 0


class OutboxPublisher:
    """Drains the transactional outbox through a delivery transport.

    The ``publisher`` port (platform ``EventPublisher`` contract) decides
    where envelopes go — realtime fan-out, webhooks, downstream workers.
    The publisher loop only owns claiming, delivery, and finalization.
    """

    def __init__(
        self,
        store: OutboxStore,
        publisher: EventPublisher,
        *,
        worker_id: str | None = None,
        batch_size: int = 50,
        lease_s: float = DEFAULT_LEASE_S,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_s: float = DEFAULT_BACKOFF_S,
        on_dead_letter: DeadLetterHook | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._worker_id = worker_id or f"outbox-publisher-{uuid4().hex[:12]}"
        self._batch_size = batch_size
        self._lease_s = lease_s
        self._max_attempts = max_attempts
        self._backoff_s = backoff_s
        self._on_dead_letter = on_dead_letter
        self._clock: Clock = clock or SystemClock()

    @property
    def worker_id(self) -> str:
        """Identity used to claim outbox records."""
        return self._worker_id

    async def publish_pending(self) -> PublishReport:
        """Claim one batch, deliver every record, finalize each outcome."""
        claimed = await self._store.claim_batch(
            worker_id=self._worker_id,
            limit=self._batch_size,
            lease_s=self._lease_s,
        )

        published = 0
        retried = 0
        dead_lettered = 0
        for record in claimed:
            assert record.claim_token is not None
            try:
                await self._publisher.publish(record.to_envelope())
            except Exception as error:  # noqa: BLE001 - failures are durable state
                finalized = await self._store.mark_failed(
                    record.id,
                    claim_token=record.claim_token,
                    error=f"{type(error).__name__}: {error}",
                    max_attempts=self._max_attempts,
                    backoff_s=self._backoff_s,
                )
                if not finalized:
                    continue  # stale claim; another publisher owns the record
                if _attempted_to_death(record, self._max_attempts):
                    dead_lettered += 1
                    await self._notify_dead_letter(record)
                else:
                    retried += 1
            else:
                if await self._store.mark_published(
                    record.id, claim_token=record.claim_token
                ):
                    published += 1

        return PublishReport(
            claimed=len(claimed),
            published=published,
            retried=retried,
            dead_lettered=dead_lettered,
        )

    async def run(
        self,
        *,
        interval_s: float = 1.0,
        stop: asyncio.Event | None = None,
    ) -> int:
        """Reclaim expired claims and drain until ``stop`` is set.

        Returns the total number of published records; designed for the
        worker foundation (Phase 7) to host in its own task.
        """
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")

        total_published = 0
        while stop is None or not stop.is_set():
            await self._store.reclaim_expired_claims()
            report = await self.publish_pending()
            total_published += report.published
            if report.idle:
                if stop is not None:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval_s)
                    except TimeoutError:
                        pass
                else:
                    await asyncio.sleep(interval_s)
        return total_published

    async def _notify_dead_letter(self, record: OutboxRecord) -> None:
        hook = self._on_dead_letter
        if hook is None:
            return
        outcome = hook(record)
        if inspect.isawaitable(outcome):
            await outcome


def _attempted_to_death(record: OutboxRecord, max_attempts: int) -> bool:
    # The store already flipped the status; infer from the attempt counter
    # captured at claim time plus this failure.
    return record.attempt_count + 1 >= max_attempts
