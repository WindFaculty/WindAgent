"""Event publisher for WindAgent Observability Layer (Phase 3 / Phase 6)."""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Set

from windagent_core.events.envelope import EventEnvelope
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepository
from windagent_observability.events.heartbeat import PublisherHeartbeat
from windagent_observability.events.retry import (
    DEFAULT_MAX_ATTEMPTS,
    compute_backoff_seconds,
    is_retryable_error,
    next_available_at,
)

logger = logging.getLogger("windagent.observability.events.publisher")


class OutboxEventPublisher:
    """Reads pending outbox records, claims them, and publishes via a dispatcher."""

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        dispatcher: Callable[[EventEnvelope], Any],
        batch_size: int = 50,
        poll_interval_seconds: float = 1.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        claim_ttl_seconds: float = 60.0,
        publisher_id: str = "outbox-publisher",
    ):
        self._outbox_repo = outbox_repo
        self._dispatcher = dispatcher
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._max_attempts = max_attempts
        self._claim_ttl_seconds = claim_ttl_seconds
        self._publisher_id = publisher_id
        self._running = False
        self._started = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._heartbeat = PublisherHeartbeat()
        self._dispatched_event_ids: Set[str] = set()

    @property
    def heartbeat(self) -> PublisherHeartbeat:
        return self._heartbeat

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._heartbeat.state = "starting"
        self._running = True
        self._started.clear()
        self._task = asyncio.create_task(self._poll_loop())
        try:
            await asyncio.wait_for(self._started.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("OutboxEventPublisher start timed out waiting for first poll.")
        self._heartbeat.state = "running"
        logger.info("OutboxEventPublisher started.")

    async def stop(self, drain: bool = False) -> None:
        if drain and self._running:
            self._heartbeat.state = "draining"
            try:
                while True:
                    count = await self.publish_pending()
                    if count == 0:
                        break
            except Exception as exc:
                logger.warning(f"Error during outbox drain: {exc}")

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._heartbeat.state = "stopped"
        logger.info("OutboxEventPublisher stopped.")

    async def publish_pending(self) -> int:
        """Claim and process one batch of pending outbox records."""
        now = datetime.now(timezone.utc)
        self._heartbeat.last_poll_at = now

        try:
            await self._outbox_repo.recover_expired_claims(now=now)
            counts = await self._outbox_repo.get_status_counts()
            self._heartbeat.pending_count = counts.get("pending", 0)
            self._heartbeat.publishing_count = counts.get("publishing", 0)
            self._heartbeat.dead_letter_count = counts.get("dead_letter", 0)
        except Exception as exc:
            logger.debug(f"Outbox heartbeat count refresh failed: {exc}")

        claim_token = f"claim_{uuid.uuid4().hex[:16]}"
        records = await self._outbox_repo.claim_pending_batch(
            limit=self._batch_size,
            claim_token=claim_token,
            claimed_by=self._publisher_id,
            now=now,
            claim_ttl_seconds=self._claim_ttl_seconds,
        )
        processed = 0

        for record in records:
            try:
                envelope = self._record_to_envelope(record)
                if str(envelope.event_id) in self._dispatched_event_ids:
                    logger.debug(f"Skipping duplicate dispatch for event_id={envelope.event_id}")
                else:
                    result = self._dispatcher(envelope)
                    if hasattr(result, "__await__"):
                        await result
                    self._dispatched_event_ids.add(str(envelope.event_id))

                await self._outbox_repo.mark_published(
                    record.id,
                    datetime.now(timezone.utc),
                    claim_token=record.claim_token,
                )
                self._heartbeat.last_success_at = datetime.now(timezone.utc)
                processed += 1
            except Exception as exc:
                logger.error(f"Failed to publish outbox record {record.id}: {exc}")
                next_attempt = record.attempt_count + 1
                if not is_retryable_error(exc) or next_attempt >= self._max_attempts:
                    await self._outbox_repo.mark_dead_letter(
                        record.id,
                        str(exc),
                        claim_token=record.claim_token,
                    )
                    self._heartbeat.dead_letter_count += 1
                else:
                    retry_at = next_available_at(next_attempt, now=now)
                    await self._outbox_repo.mark_failed(
                        record.id,
                        str(exc),
                        retry_at,
                        claim_token=record.claim_token,
                    )
                    self._heartbeat.failed_count += 1
        self._heartbeat.pending_count = max(0, self._heartbeat.pending_count - processed)
        self._heartbeat.publishing_count = max(0, self._heartbeat.publishing_count - len(records))
        return processed

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                count = await self.publish_pending()
                if count > 0:
                    logger.debug(f"Published {count} outbox events.")
            except Exception as exc:
                logger.error(f"Outbox poll error: {exc}")
            finally:
                self._started.set()
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
