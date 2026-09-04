"""Phase 6 integration: event + outbox semantics on real PostgreSQL.

Requires the canonical database (``docker compose up -d postgres``) and is
skipped automatically when it is unreachable.  CI runs these tests against
a dedicated PostgreSQL 16 service container.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select, text
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import ActorId, CorrelationId, EntityId
from windagent.platform.events import (
    OUTBOX_STATUS_PUBLISHED,
    OutboxPublisher,
    OutboxStore,
    TransactionalOutbox,
    outbox_table,
)
from windagent.platform.persistence import Database, SqlUnitOfWork

pytestmark = [pytest.mark.postgres]


class TransportPublisher:
    """Fake delivery transport implementing the EventPublisher contract."""

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.delivered: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("transport down")
        self.delivered.append(event)


async def test_transactional_outbox_end_to_end(database: Database) -> None:
    """Domain change + outbox event + COMMIT, then the publisher drains it."""
    envelope = EventEnvelope(
        event_type="studio.episode.planned",
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=0,
        payload={"title": "ep1"},
        actor_id=ActorId.new(),
        correlation_id=CorrelationId.new(),
    )

    unit_of_work = SqlUnitOfWork(database.session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        first = await outbox.record(envelope, deduplication_key="integration:1")
        duplicate = await outbox.record(envelope, deduplication_key="integration:1")
        await unit_of_work.commit()

    assert first is True
    assert duplicate is False

    transport = TransportPublisher()
    publisher = OutboxPublisher(OutboxStore(database.session_factory), transport)
    report = await publisher.publish_pending()

    assert report.published == 1
    delivered = transport.delivered[0]
    assert delivered.event_id == envelope.event_id
    assert delivered.correlation_id == envelope.correlation_id
    assert delivered.payload == envelope.payload

    async with database.session_factory() as session:
        row = (
            await session.execute(
                select(outbox_table).where(
                    outbox_table.c.event_id == str(envelope.event_id)
                )
            )
        ).one()
    assert row.status == OUTBOX_STATUS_PUBLISHED

    # The deduplication key stays resident: re-recording is a no-op.
    unit_of_work = SqlUnitOfWork(database.session_factory)
    async with unit_of_work:
        replay = await TransactionalOutbox(unit_of_work).record(
            envelope, deduplication_key="integration:1"
        )
        await unit_of_work.rollback()  # nothing new should have been written
    assert replay is False


async def test_outbox_claim_uses_skip_locked_on_postgres(database: Database) -> None:
    """Two concurrent claim scans never share a record."""
    unit_of_work = SqlUnitOfWork(database.session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        for _ in range(4):
            await outbox.record_next(
                EventEnvelope(
                    event_type="studio.episode.planned",
                    aggregate_type="episode",
                    aggregate_id=EntityId.new(),
                    sequence=0,
                )
            )
        await unit_of_work.commit()

    store = OutboxStore(database.session_factory)

    async def claim(worker_id: str) -> list[str]:
        claimed = await store.claim_batch(worker_id=worker_id, limit=10)
        return [record.event_id.value for record in claimed]

    first_ids, second_ids = await asyncio.gather(claim("w1"), claim("w2"))

    overlap = set(first_ids) & set(second_ids)
    assert overlap == set()
    assert len(first_ids) + len(second_ids) == 4

    report = await OutboxPublisher(store, TransportPublisher()).publish_pending()
    assert report.idle is True  # everything already claimed by the two scans


async def test_failed_delivery_retries_and_recovers(database: Database) -> None:
    envelope = EventEnvelope(
        event_type="studio.episode.planned",
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=0,
    )
    unit_of_work = SqlUnitOfWork(database.session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(envelope)
        await unit_of_work.commit()

    transport = TransportPublisher(failures=1)
    publisher = OutboxPublisher(
        OutboxStore(database.session_factory),
        transport,
        backoff_s=0.0,
    )

    first = await publisher.publish_pending()
    assert first.retried == 1
    second = await publisher.publish_pending()
    assert second.published == 1

    async with database.session_factory() as session:
        row = (
            await session.execute(
                select(outbox_table).where(
                    outbox_table.c.event_id == str(envelope.event_id)
                )
            )
        ).one()
    assert row.status == OUTBOX_STATUS_PUBLISHED
    assert row.attempt_count == 1


async def test_stream_tables_store_canonical_columns(database: Database) -> None:
    """Timestamps survive the round trip as UTC timestamptz values."""
    envelope = EventEnvelope(
        event_type="studio.episode.planned",
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=0,
        payload={"title": "ep1"},
    )
    unit_of_work = SqlUnitOfWork(database.session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(envelope)
        await unit_of_work.commit()

    async with database.session_factory() as session:
        result = await session.execute(
            text(
                "SELECT occurred_at AT TIME ZONE 'UTC' AS utc_ts FROM platform_events "
                "WHERE event_id = :event_id"
            ),
            {"event_id": str(envelope.event_id)},
        )
    utc_ts = result.scalar_one()
    assert utc_ts.year == envelope.occurred_at.year
    assert utc_ts.month == envelope.occurred_at.month
    assert utc_ts.day == envelope.occurred_at.day
    assert utc_ts.hour == envelope.occurred_at.hour
