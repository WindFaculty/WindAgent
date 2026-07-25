"""Event publisher for WindAgent Observability Layer (Phase 3)."""

from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

from windagent_core.events.envelope import EventEnvelope
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepository

logger = logging.getLogger("windagent.observability.events.publisher")


class OutboxEventPublisher:
    """Reads pending outbox records and publishes them via a dispatcher."""

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        dispatcher: Callable[[EventEnvelope], Any],
        batch_size: int = 50,
        poll_interval_seconds: float = 1.0,
    ):
        self._outbox_repo = outbox_repo
        self._dispatcher = dispatcher
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("OutboxEventPublisher started.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("OutboxEventPublisher stopped.")

    async def publish_pending(self) -> int:
        """Process one batch of pending outbox records. Returns count processed."""
        now = datetime.now(timezone.utc)
        records = await self._outbox_repo.get_pending(limit=self._batch_size, now=now)
        processed = 0

        for record in records:
            try:
                envelope = self._record_to_envelope(record)
                result = self._dispatcher(envelope)
                if hasattr(result, "__await__"):
                    await result
                await self._outbox_repo.mark_published(record.id, datetime.now(timezone.utc))
                processed += 1
            except Exception as exc:
                logger.error(f"Failed to publish outbox record {record.id}: {exc}")
                next_available = datetime.now(timezone.utc) + timedelta(seconds=2 ** record.attempt_count)
                if record.attempt_count >= 5:
                    await self._outbox_repo.mark_dead_letter(record.id, str(exc))
                else:
                    await self._outbox_repo.mark_failed(record.id, str(exc), next_available)

        return processed

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                count = await self.publish_pending()
                if count > 0:
                    logger.debug(f"Published {count} outbox events.")
            except Exception as exc:
                logger.error(f"Outbox poll error: {exc}")
            await asyncio.sleep(self._poll_interval)

    def _record_to_envelope(self, record: OutboxRecord) -> EventEnvelope:
        payload = json.loads(record.payload_json) if record.payload_json else {}
        return EventEnvelope(
            event_id=record.event_id,
            event_type=record.event_type,
            schema_version=record.schema_version,
            aggregate_id=record.aggregate_id,
            aggregate_type=record.aggregate_type,
            sequence=record.sequence_number,
            occurred_at=record.created_at,
            payload=payload,
        )
