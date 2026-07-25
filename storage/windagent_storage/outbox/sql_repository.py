"""SQL implementation of OutboxRepository for WindAgent Storage Layer (Phase 5).

Supports both SessionFactory-scoped execution (Publisher loop) and Session-scoped execution (UOW).
"""

from __future__ import annotations
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional, Union

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepositoryPort


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SqlOutboxRepository(OutboxRepositoryPort):
    """SQL-backed outbox repository supporting both Session-scoped and SessionFactory-scoped execution."""

    def __init__(self, session_or_factory: Union[AsyncSession, async_sessionmaker[AsyncSession]]):
        if hasattr(session_or_factory, "__call__"):
            self._session_factory: Optional[async_sessionmaker[AsyncSession]] = session_or_factory
            self._session: Optional[AsyncSession] = None
        else:
            self._session_factory = None
            self._session = session_or_factory

    @asynccontextmanager
    async def _get_session(self):
        if self._session_factory is not None:
            async with self._session_factory() as session:
                async with session.begin():
                    yield session
        else:
            yield self._session

    async def save(self, record: OutboxRecord) -> None:
        async with self._get_session() as session:
            created_at = record.created_at.replace(tzinfo=None) if record.created_at and record.created_at.tzinfo else record.created_at
            available_at = record.available_at.replace(tzinfo=None) if record.available_at and record.available_at.tzinfo else record.available_at
            published_at = record.published_at.replace(tzinfo=None) if record.published_at and record.published_at.tzinfo else record.published_at

            orm = OutboxRecordORM(
                id=record.id,
                event_id=record.event_id,
                aggregate_id=record.aggregate_id,
                aggregate_type=record.aggregate_type,
                event_type=record.event_type,
                payload_json=record.payload_json,
                schema_version=record.schema_version,
                sequence_number=record.sequence_number,
                created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
                available_at=available_at or datetime.now(timezone.utc).replace(tzinfo=None),
                published_at=published_at,
                attempt_count=record.attempt_count,
                last_error=record.last_error,
                status=record.status,
                deduplication_key=record.deduplication_key,
            )
            await session.merge(orm)

    async def get_pending(self, limit: int = 50, now: Optional[datetime] = None) -> List[OutboxRecord]:
        now_dt = (now or _default_utc_now()).replace(tzinfo=None)
        async with self._get_session() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.status == "pending")
                .where(OutboxRecordORM.available_at <= now_dt)
                .order_by(OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            orms = res.scalars().all()
            return [self._orm_to_model(o) for o in orms]

    async def get_by_id(self, record_id: str) -> Optional[OutboxRecord]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
            res = await session.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def mark_published(self, record_id: str, published_at: Optional[datetime] = None) -> None:
        published_dt = (published_at or _default_utc_now()).replace(tzinfo=None)
        async with self._get_session() as session:
            stmt = (
                update(OutboxRecordORM)
                .where(OutboxRecordORM.id == record_id)
                .values(status="published", published_at=published_dt)
            )
            await session.execute(stmt)

    async def mark_failed(self, record_id: str, error: str, next_available_at: Optional[datetime] = None) -> None:
        next_dt = (next_available_at or _default_utc_now()).replace(tzinfo=None)
        async with self._get_session() as session:
            stmt = (
                update(OutboxRecordORM)
                .where(OutboxRecordORM.id == record_id)
                .values(
                    status="pending",
                    last_error=error,
                    available_at=next_dt,
                    attempt_count=OutboxRecordORM.attempt_count + 1,
                )
            )
            await session.execute(stmt)

    async def mark_dead_letter(self, record_id: str, error: str) -> None:
        async with self._get_session() as session:
            stmt = (
                update(OutboxRecordORM)
                .where(OutboxRecordORM.id == record_id)
                .values(status="dead_letter", last_error=error)
            )
            await session.execute(stmt)

    async def get_by_deduplication_key(self, dedup_key: str) -> Optional[OutboxRecord]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM).where(OutboxRecordORM.deduplication_key == dedup_key)
            res = await session.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_by_aggregate(self, aggregate_id: str, limit: int = 100) -> List[OutboxRecord]:
        async with self._get_session() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.aggregate_id == aggregate_id)
                .order_by(OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            orms = res.scalars().all()
            return [self._orm_to_model(o) for o in orms]

    def _orm_to_model(self, orm: OutboxRecordORM) -> OutboxRecord:
        created = orm.created_at.replace(tzinfo=timezone.utc) if orm.created_at and orm.created_at.tzinfo is None else orm.created_at
        available = orm.available_at.replace(tzinfo=timezone.utc) if orm.available_at and orm.available_at.tzinfo is None else orm.available_at
        published = orm.published_at.replace(tzinfo=timezone.utc) if orm.published_at and orm.published_at.tzinfo is None else orm.published_at

        return OutboxRecord(
            id=orm.id,
            event_id=orm.event_id,
            aggregate_id=orm.aggregate_id,
            aggregate_type=orm.aggregate_type,
            event_type=orm.event_type,
            payload_json=orm.payload_json,
            schema_version=orm.schema_version,
            sequence_number=orm.sequence_number,
            created_at=created,
            available_at=available,
            published_at=published,
            attempt_count=orm.attempt_count,
            last_error=orm.last_error,
            status=orm.status,
            deduplication_key=orm.deduplication_key,
        )
