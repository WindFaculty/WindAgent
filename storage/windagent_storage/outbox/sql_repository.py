"""SQL implementation of OutboxRepository for WindAgent Storage Layer (Phase 3)."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepository


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SqlOutboxRepository:
    """SQL-backed outbox repository with optimistic claim support."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, record: OutboxRecord) -> None:
        orm = OutboxRecordORM(
            id=record.id,
            event_id=record.event_id,
            aggregate_id=record.aggregate_id,
            aggregate_type=record.aggregate_type,
            event_type=record.event_type,
            payload_json=record.payload_json,
            schema_version=record.schema_version,
            sequence_number=record.sequence_number,
            created_at=record.created_at,
            available_at=record.available_at,
            published_at=record.published_at,
            attempt_count=record.attempt_count,
            last_error=record.last_error,
            status=record.status,
            deduplication_key=record.deduplication_key,
        )
        await self._session.merge(orm)

    async def get_pending(self, limit: int = 50, now: Optional[datetime] = None) -> List[OutboxRecord]:
        now = now or _default_utc_now()
        stmt = (
            select(OutboxRecordORM)
            .where(OutboxRecordORM.status == "pending")
            .where(OutboxRecordORM.available_at <= now)
            .order_by(OutboxRecordORM.sequence_number.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [self._orm_to_model(o) for o in orms]

    async def get_by_id(self, record_id: str) -> Optional[OutboxRecord]:
        stmt = select(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._orm_to_model(orm) if orm else None

    async def mark_published(self, record_id: str, published_at: datetime) -> None:
        stmt = (
            update(OutboxRecordORM)
            .where(OutboxRecordORM.id == record_id)
            .values(status="published", published_at=published_at)
        )
        await self._session.execute(stmt)

    async def mark_failed(self, record_id: str, error: str, next_available_at: datetime) -> None:
        stmt = (
            update(OutboxRecordORM)
            .where(OutboxRecordORM.id == record_id)
            .values(
                status="pending",
                last_error=error,
                available_at=next_available_at,
                attempt_count=OutboxRecordORM.attempt_count + 1,
            )
        )
        await self._session.execute(stmt)

    async def mark_dead_letter(self, record_id: str, error: str) -> None:
        stmt = (
            update(OutboxRecordORM)
            .where(OutboxRecordORM.id == record_id)
            .values(status="dead_letter", last_error=error)
        )
        await self._session.execute(stmt)

    async def get_by_deduplication_key(self, dedup_key: str) -> Optional[OutboxRecord]:
        stmt = select(OutboxRecordORM).where(OutboxRecordORM.deduplication_key == dedup_key)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._orm_to_model(orm) if orm else None

    async def get_by_aggregate(self, aggregate_id: str, limit: int = 100) -> List[OutboxRecord]:
        stmt = (
            select(OutboxRecordORM)
            .where(OutboxRecordORM.aggregate_id == aggregate_id)
            .order_by(OutboxRecordORM.sequence_number.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [self._orm_to_model(o) for o in orms]

    def _orm_to_model(self, orm: OutboxRecordORM) -> OutboxRecord:
        return OutboxRecord(
            id=orm.id,
            event_id=orm.event_id,
            aggregate_id=orm.aggregate_id,
            aggregate_type=orm.aggregate_type,
            event_type=orm.event_type,
            payload_json=orm.payload_json,
            schema_version=orm.schema_version,
            sequence_number=orm.sequence_number,
            created_at=orm.created_at,
            available_at=orm.available_at,
            published_at=orm.published_at,
            attempt_count=orm.attempt_count,
            last_error=orm.last_error,
            status=orm.status,
            deduplication_key=orm.deduplication_key,
        )
