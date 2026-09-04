"""Transactional outbox: event store + outbox tables and their adapters.

Preserved semantics from the old system: the event-store append and the
outbox write happen inside the caller's unit-of-work transaction (with the
``after_event_write`` crash gate between them), records carry claim fields
for lease-style publication, and ``deduplication_key`` provides idempotent
recording.  The publisher claims via a guarded status flip — the same
``pending → publishing → published | dead_letter`` flow.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    case,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId, EventId
from windagent.kernel.time import Clock, SystemClock, normalize_utc
from windagent.kernel.types import JSONValue, thaw_json
from windagent.kernel.types.version import Version
from windagent.platform.persistence.metadata import metadata
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

CHECKPOINT_AFTER_EVENT_WRITE = "after_event_write"

OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_PUBLISHING = "publishing"
OUTBOX_STATUS_PUBLISHED = "published"
OUTBOX_STATUS_DEAD_LETTER = "dead_letter"

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_S = 2.0
DEFAULT_LEASE_S = 30.0


# --------------------------------------------------------------------------- #
# Tables (registered into the shared Alembic autogenerate metadata)
# --------------------------------------------------------------------------- #

events_table = Table(
    "platform_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("event_type", String(200), nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("aggregate_type", String(100), nullable=False),
    Column("aggregate_id", String(36), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("actor_id", String(36), nullable=True),
    Column("correlation_id", String(36), nullable=True),
    Column("causation_id", String(36), nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("payload_json", Text, nullable=False),
    UniqueConstraint(
        "aggregate_type",
        "aggregate_id",
        "sequence",
        name="uq_platform_events_stream",
    ),
)

outbox_table = Table(
    "platform_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("event_id", String(36), nullable=False, index=True),
    Column("event_type", String(200), nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("aggregate_type", String(100), nullable=False),
    Column("aggregate_id", String(36), nullable=False),
    Column("sequence_number", Integer, nullable=False),
    Column("actor_id", String(36), nullable=True),
    Column("correlation_id", String(36), nullable=True),
    Column("causation_id", String(36), nullable=True),
    Column("payload_json", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("last_error", Text, nullable=True),
    Column("status", String(20), nullable=False, default=OUTBOX_STATUS_PENDING),
    Column("deduplication_key", String(200), nullable=True),
    Column("claimed_by", String(100), nullable=True),
    Column("claim_token", String(36), nullable=True),
    Column("claim_expires_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("deduplication_key", name="uq_platform_outbox_dedup"),
)


# --------------------------------------------------------------------------- #
# Record model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    """One durable outbox row, read-side model of ``platform_outbox``."""

    id: str
    event_id: EventId
    event_type: str
    event_version: Version
    aggregate_type: str
    aggregate_id: EntityId
    sequence_number: int
    payload: Mapping[str, JSONValue]
    occurred_at: datetime
    created_at: datetime
    available_at: datetime
    actor_id: ActorId | None = None
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None
    attempt_count: int = 0
    status: str = OUTBOX_STATUS_PENDING
    published_at: datetime | None = None
    last_error: str | None = None
    deduplication_key: str | None = None
    claimed_by: str | None = None
    claim_token: str | None = None
    claim_expires_at: datetime | None = None

    def to_envelope(self) -> EventEnvelope:
        """Reconstruct the canonical envelope for delivery.

        Actor, correlation and causation identifiers round-trip through the
        outbox so downstream consumers keep the causal chain (an intentional
        V2 improvement documented in ADR-0003).
        """
        return EventEnvelope(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=self.aggregate_id,
            sequence=self.sequence_number,
            payload=self.payload,
            event_id=self.event_id,
            event_version=self.event_version,
            occurred_at=self.occurred_at,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
        )


# --------------------------------------------------------------------------- #
# Transactional writer (joins the caller's unit of work)
# --------------------------------------------------------------------------- #


class TransactionalOutbox:
    """Records envelopes into the event store + outbox atomically.

    Must be used inside an active unit-of-work scope: the caller opens
    ``async with database.unit_of_work() as uow``, records events, performs
    the domain change on the same session, and commits once.  A crash
    anywhere before commit rolls back the event and the outbox row together.
    """

    def __init__(
        self,
        unit_of_work: SqlUnitOfWork,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock: Clock = clock or SystemClock()

    async def record(
        self,
        envelope: EventEnvelope,
        *,
        deduplication_key: str | None = None,
    ) -> bool:
        """Append the envelope to the event store and the outbox.

        Returns ``True`` when the event was recorded and ``False`` when a
        record with the same ``deduplication_key`` already exists — the
        old finalizer's idempotency semantics.
        """
        session = self._unit_of_work.session
        now = self._clock.now()

        if deduplication_key is not None:
            existing = await session.execute(
                select(outbox_table.c.id).where(
                    outbox_table.c.deduplication_key == deduplication_key
                )
            )
            if existing.first() is not None:
                return False

        await session.execute(
            insert(events_table).values(_event_row(envelope))
        )

        # Old Phase 5A crash gate, preserved at exactly the same point: after
        # the event-store append and before the outbox write.  A crash here
        # must roll back both.
        await self._unit_of_work.checkpoint(CHECKPOINT_AFTER_EVENT_WRITE)

        await session.execute(
            insert(outbox_table).values(
                {
                    "id": str(uuid4()),
                    "event_id": str(envelope.event_id),
                    "event_type": envelope.event_type,
                    "event_version": int(envelope.event_version),
                    "aggregate_type": envelope.aggregate_type,
                    "aggregate_id": str(envelope.aggregate_id),
                    "sequence_number": envelope.sequence,
                    "actor_id": str(envelope.actor_id) if envelope.actor_id else None,
                    "correlation_id": (
                        str(envelope.correlation_id) if envelope.correlation_id else None
                    ),
                    "causation_id": (
                        str(envelope.causation_id) if envelope.causation_id else None
                    ),
                    "payload_json": json.dumps(thaw_json(envelope.payload)),
                    "occurred_at": normalize_utc(envelope.occurred_at),
                    "created_at": now,
                    "available_at": now,
                    "attempt_count": 0,
                    "status": OUTBOX_STATUS_PENDING,
                    "deduplication_key": deduplication_key,
                }
            )
        )
        return True

    async def record_next(
        self,
        envelope: EventEnvelope,
        *,
        deduplication_key: str | None = None,
    ) -> bool:
        """Record the envelope with the next sequence of its stream.

        Mirrors the old event store: ``max(sequence) + 1`` per aggregate
        stream, allocated inside the caller's transaction.  The stream
        unique constraint is the concurrency backstop.
        """
        sequence = await self.next_sequence(
            envelope.aggregate_type, envelope.aggregate_id
        )
        return await self.record(
            replace(envelope, sequence=sequence),
            deduplication_key=deduplication_key,
        )

    async def next_sequence(self, aggregate_type: str, aggregate_id: EntityId) -> int:
        """Return the next free sequence number for the aggregate stream."""
        session = self._unit_of_work.session
        result = await session.execute(
            select(func.max(events_table.c.sequence)).where(
                events_table.c.aggregate_type == aggregate_type,
                events_table.c.aggregate_id == str(aggregate_id),
            )
        )
        current = result.scalar()
        return (current if current is not None else -1) + 1


# --------------------------------------------------------------------------- #
# Read/claim side (drives the publisher)
# --------------------------------------------------------------------------- #


class OutboxStore:
    """Claim-and-finalize access to pending outbox rows.

    Owns short-lived sessions independent of domain unit-of-work scopes:
    claiming and marking happen in their own transactions so delivery never
    runs inside a database transaction.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock: Clock = clock or SystemClock()

    async def claim_batch(
        self,
        *,
        worker_id: str,
        limit: int = 50,
        lease_s: float = DEFAULT_LEASE_S,
    ) -> tuple[OutboxRecord, ...]:
        """Atomically claim up to ``limit`` deliverable records.

        Deliverable means ``pending`` with ``available_at <= now``, oldest
        stream position first.  On PostgreSQL the scan uses
        ``FOR UPDATE SKIP LOCKED``; everywhere else the guarded status flip
        alone guarantees single ownership.  Claims expire after ``lease_s``.
        """
        now = self._clock.now()
        claim_token = str(uuid4())
        claimed: list[OutboxRecord] = []

        async with self._session_factory() as session:
            scan = (
                select(outbox_table)
                .where(outbox_table.c.status == OUTBOX_STATUS_PENDING)
                .where(outbox_table.c.available_at <= now)
                .order_by(
                    outbox_table.c.aggregate_id.asc(),
                    outbox_table.c.sequence_number.asc(),
                )
                .limit(limit)
            )
            if _supports_skip_locked(session):
                scan = scan.with_for_update(skip_locked=True)

            rows = (await session.execute(scan)).all()
            for row in rows:
                flip = (
                    update(outbox_table)
                    .where(
                        outbox_table.c.id == row.id,
                        outbox_table.c.status == OUTBOX_STATUS_PENDING,
                    )
                    .values(
                        status=OUTBOX_STATUS_PUBLISHING,
                        claimed_by=worker_id,
                        claim_token=claim_token,
                        claim_expires_at=now + timedelta(seconds=lease_s),
                    )
                )
                outcome = cast("CursorResult[Any]", await session.execute(flip))
                if outcome.rowcount == 1:
                    claimed.append(
                        _record_from_row(
                            row,
                            status=OUTBOX_STATUS_PUBLISHING,
                            claim_token=claim_token,
                            claimed_by=worker_id,
                            claim_expires_at=now + timedelta(seconds=lease_s),
                        )
                    )
            await session.commit()

        return tuple(claimed)

    async def mark_published(self, record_id: str, *, claim_token: str) -> bool:
        """Finalize a claimed record as published (claim-token CAS)."""
        statement = (
            update(outbox_table)
            .where(
                outbox_table.c.id == record_id,
                outbox_table.c.status == OUTBOX_STATUS_PUBLISHING,
                outbox_table.c.claim_token == claim_token,
            )
            .values(
                status=OUTBOX_STATUS_PUBLISHED,
                published_at=self._clock.now(),
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
            )
        )
        async with self._session_factory() as session:
            outcome = cast("CursorResult[Any]", await session.execute(statement))
            await session.commit()
        return outcome.rowcount == 1

    async def mark_failed(
        self,
        record_id: str,
        *,
        claim_token: str,
        error: str,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_s: float = DEFAULT_BACKOFF_S,
    ) -> bool:
        """Record a delivery failure and schedule the retry.

        The attempt counter is incremented in the same statement; once
        ``max_attempts`` is reached the record moves to ``dead_letter``
        instead of back to ``pending``.  Returns ``False`` when another
        publisher owns the record (stale claim).
        """
        now = self._clock.now()
        attempts_after = outbox_table.c.attempt_count + 1
        statement = (
            update(outbox_table)
            .where(
                outbox_table.c.id == record_id,
                outbox_table.c.status == OUTBOX_STATUS_PUBLISHING,
                outbox_table.c.claim_token == claim_token,
            )
            .values(
                attempt_count=attempts_after,
                last_error=error,
                status=case(
                    (attempts_after >= max_attempts, OUTBOX_STATUS_DEAD_LETTER),
                    else_=OUTBOX_STATUS_PENDING,
                ),
                available_at=now + timedelta(seconds=backoff_s),
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
            )
        )
        async with self._session_factory() as session:
            outcome = cast("CursorResult[Any]", await session.execute(statement))
            await session.commit()
        return outcome.rowcount == 1

    async def reclaim_expired_claims(self) -> int:
        """Return expired ``publishing`` claims to ``pending``.

        Recovery path for crashed publishers: a record whose lease elapsed
        becomes claimable again, exactly like the old claim fields implied.
        """
        now = self._clock.now()
        statement = (
            update(outbox_table)
            .where(
                outbox_table.c.status == OUTBOX_STATUS_PUBLISHING,
                outbox_table.c.claim_expires_at < now,
            )
            .values(
                status=OUTBOX_STATUS_PENDING,
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
            )
        )
        async with self._session_factory() as session:
            outcome = cast("CursorResult[Any]", await session.execute(statement))
            await session.commit()
        return outcome.rowcount

    async def count_by_status(self) -> dict[str, int]:
        """Row counts per status; consumed by health and metrics."""
        async with self._session_factory() as session:
            rows = await session.execute(
                select(outbox_table.c.status, func.count())
                .group_by(outbox_table.c.status)
            )
            return {status: int(count) for status, count in rows.all()}


def _supports_skip_locked(session: AsyncSession) -> bool:
    engine = session.bind
    return engine is not None and engine.dialect.name == "postgresql"


def as_utc(value: datetime) -> datetime:
    """Attach UTC to dialect-naive datetimes (values are always stored UTC).

    Public so tests and future adapters normalize raw rows the same way the
    outbox adapter does.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _event_row(envelope: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": str(envelope.event_id),
        "event_type": envelope.event_type,
        "event_version": int(envelope.event_version),
        "aggregate_type": envelope.aggregate_type,
        "aggregate_id": str(envelope.aggregate_id),
        "sequence": envelope.sequence,
        "actor_id": str(envelope.actor_id) if envelope.actor_id else None,
        "correlation_id": str(envelope.correlation_id) if envelope.correlation_id else None,
        "causation_id": str(envelope.causation_id) if envelope.causation_id else None,
        "occurred_at": normalize_utc(envelope.occurred_at),
        "payload_json": json.dumps(thaw_json(envelope.payload)),
    }


def _record_from_row(
    row: Any,
    *,
    status: str | None = None,
    claim_token: str | None = None,
    claimed_by: str | None = None,
    claim_expires_at: datetime | None = None,
) -> OutboxRecord:
    raw_payload = json.loads(row.payload_json) if row.payload_json else {}
    payload = cast("Mapping[str, JSONValue]", raw_payload)
    return OutboxRecord(
        id=row.id,
        event_id=EventId(row.event_id),
        event_type=row.event_type,
        event_version=Version(row.event_version),
        aggregate_type=row.aggregate_type,
        aggregate_id=EntityId(row.aggregate_id),
        sequence_number=row.sequence_number,
        payload=payload,
        occurred_at=as_utc(row.occurred_at),
        created_at=as_utc(row.created_at),
        available_at=as_utc(row.available_at),
        actor_id=ActorId(row.actor_id) if row.actor_id else None,
        correlation_id=CorrelationId(row.correlation_id) if row.correlation_id else None,
        causation_id=CausationId(row.causation_id) if row.causation_id else None,
        attempt_count=row.attempt_count,
        status=status if status is not None else row.status,
        published_at=as_utc(row.published_at) if row.published_at else None,
        last_error=row.last_error,
        deduplication_key=row.deduplication_key,
        claimed_by=claimed_by if claimed_by is not None else row.claimed_by,
        claim_token=claim_token if claim_token is not None else row.claim_token,
        claim_expires_at=(
            normalize_utc(claim_expires_at)
            if claim_expires_at is not None
            else (as_utc(row.claim_expires_at) if row.claim_expires_at else None)
        ),
    )
