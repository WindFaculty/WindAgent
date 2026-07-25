"""SQL implementation of OutboxRepository for WindAgent Storage Layer (Phase 5 / Phase 6).

Supports both SessionFactory-scoped execution (Publisher loop) and Session-scoped execution (UOW).
"""

from __future__ import annotations
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Union

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_storage.orm.models import OutboxRecordORM, OutboxReplayAuditORM
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepositoryPort


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


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
            orm = OutboxRecordORM(
                id=record.id,
                event_id=record.event_id,
                aggregate_id=record.aggregate_id,
                aggregate_type=record.aggregate_type,
                event_type=record.event_type,
                payload_json=record.payload_json,
                schema_version=record.schema_version,
                sequence_number=record.sequence_number,
                created_at=_naive(record.created_at or _default_utc_now()),
                available_at=_naive(record.available_at or _default_utc_now()),
                published_at=_naive(record.published_at) if record.published_at else None,
                attempt_count=record.attempt_count,
                last_error=record.last_error,
                status=record.status,
                deduplication_key=record.deduplication_key,
                claimed_by=record.claimed_by,
                claim_token=record.claim_token,
                claim_expires_at=_naive(record.claim_expires_at) if record.claim_expires_at else None,
            )
            await session.merge(orm)

    async def get_pending(self, limit: int = 50, now: Optional[datetime] = None) -> List[OutboxRecord]:
        now_dt = _naive(now or _default_utc_now())
        async with self._get_session() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.status == "pending")
                .where(OutboxRecordORM.available_at <= now_dt)
                .order_by(OutboxRecordORM.aggregate_id.asc(), OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            return [self._orm_to_model(o) for o in res.scalars().all()]

    async def get_by_id(self, record_id: str) -> Optional[OutboxRecord]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
            res = await session.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_by_event_id(self, event_id: str) -> Optional[OutboxRecord]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM).where(OutboxRecordORM.event_id == event_id)
            res = await session.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def mark_published(
        self,
        record_id: str,
        published_at: Optional[datetime] = None,
        claim_token: Optional[str] = None,
    ) -> None:
        published_dt = _naive(published_at or _default_utc_now())
        async with self._get_session() as session:
            stmt = update(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
            if claim_token is not None:
                stmt = stmt.where(OutboxRecordORM.claim_token == claim_token)
            stmt = stmt.values(
                status="published",
                published_at=published_dt,
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
            )
            await session.execute(stmt)

    async def mark_failed(
        self,
        record_id: str,
        error: str,
        next_available_at: Optional[datetime] = None,
        claim_token: Optional[str] = None,
    ) -> None:
        next_dt = _naive(next_available_at or _default_utc_now())
        async with self._get_session() as session:
            stmt = update(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
            if claim_token is not None:
                stmt = stmt.where(OutboxRecordORM.claim_token == claim_token)
            stmt = stmt.values(
                status="pending",
                last_error=error,
                available_at=next_dt,
                attempt_count=OutboxRecordORM.attempt_count + 1,
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
            )
            await session.execute(stmt)

    async def mark_dead_letter(
        self,
        record_id: str,
        error: str,
        claim_token: Optional[str] = None,
    ) -> None:
        async with self._get_session() as session:
            stmt = update(OutboxRecordORM).where(OutboxRecordORM.id == record_id)
            if claim_token is not None:
                stmt = stmt.where(OutboxRecordORM.claim_token == claim_token)
            stmt = stmt.values(
                status="dead_letter",
                last_error=error,
                claimed_by=None,
                claim_token=None,
                claim_expires_at=None,
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
            return [self._orm_to_model(o) for o in res.scalars().all()]

    async def claim_pending_batch(
        self,
        limit: int,
        claim_token: str,
        claimed_by: str,
        now: Optional[datetime] = None,
        claim_ttl_seconds: float = 60.0,
    ) -> List[OutboxRecord]:
        now_dt = _naive(now or _default_utc_now())
        expires_at = now_dt + timedelta(seconds=claim_ttl_seconds)
        async with self._get_session() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.status == "pending")
                .where(OutboxRecordORM.available_at <= now_dt)
                .order_by(OutboxRecordORM.aggregate_id.asc(), OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            candidates = res.scalars().all()
            claimed: List[OutboxRecord] = []
            for record in candidates:
                claim_stmt = (
                    update(OutboxRecordORM)
                    .where(OutboxRecordORM.id == record.id)
                    .where(OutboxRecordORM.status == "pending")
                    .values(
                        status="publishing",
                        claimed_by=claimed_by,
                        claim_token=claim_token,
                        claim_expires_at=expires_at,
                    )
                )
                result = await session.execute(claim_stmt)
                if result.rowcount == 1:
                    record.status = "publishing"
                    record.claimed_by = claimed_by
                    record.claim_token = claim_token
                    record.claim_expires_at = expires_at
                    claimed.append(self._orm_to_model(record))
            return claimed

    async def recover_expired_claims(self, now: Optional[datetime] = None) -> int:
        now_dt = _naive(now or _default_utc_now())
        async with self._get_session() as session:
            stmt = (
                update(OutboxRecordORM)
                .where(OutboxRecordORM.status == "publishing")
                .where(OutboxRecordORM.claim_expires_at <= now_dt)
                .values(
                    status="pending",
                    claimed_by=None,
                    claim_token=None,
                    claim_expires_at=None,
                )
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def get_dead_letters(self, limit: int = 100) -> List[OutboxRecord]:
        async with self._get_session() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.status == "dead_letter")
                .order_by(OutboxRecordORM.created_at.desc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            return [self._orm_to_model(o) for o in res.scalars().all()]

    async def get_status_counts(self) -> Dict[str, int]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM.status, func.count()).group_by(OutboxRecordORM.status)
            res = await session.execute(stmt)
            counts = {status: count for status, count in res.all()}
            return {
                "pending": counts.get("pending", 0),
                "publishing": counts.get("publishing", 0),
                "published": counts.get("published", 0),
                "dead_letter": counts.get("dead_letter", 0),
            }

    async def replay_dead_letter(
        self,
        event_id: str,
        replay_attempt_id: str,
        operator: Optional[str] = None,
    ) -> Optional[OutboxRecord]:
        async with self._get_session() as session:
            stmt = select(OutboxRecordORM).where(OutboxRecordORM.event_id == event_id)
            res = await session.execute(stmt)
            orm = res.scalar_one_or_none()
            if orm is None or orm.status != "dead_letter":
                return None

            audit = OutboxReplayAuditORM(
                id=f"audit_{uuid.uuid4().hex[:12]}",
                outbox_record_id=orm.id,
                event_id=orm.event_id,
                replay_attempt_id=replay_attempt_id,
                operator=operator,
                previous_status=orm.status,
                previous_attempt_count=orm.attempt_count,
                created_at=_naive(_default_utc_now()),
            )
            session.add(audit)

            orm.status = "pending"
            orm.available_at = _naive(_default_utc_now())
            orm.claimed_by = None
            orm.claim_token = None
            orm.claim_expires_at = None
            # Preserve attempt_count and last_error — do not reset history silently

            await session.flush()
            return self._orm_to_model(orm)

    def _orm_to_model(self, orm: OutboxRecordORM) -> OutboxRecord:
        def _aware(dt: Optional[datetime]) -> Optional[datetime]:
            if dt is None:
                return None
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

        return OutboxRecord(
            id=orm.id,
            event_id=orm.event_id,
            aggregate_id=orm.aggregate_id,
            aggregate_type=orm.aggregate_type,
            event_type=orm.event_type,
            payload_json=orm.payload_json,
            schema_version=orm.schema_version,
            sequence_number=orm.sequence_number,
            created_at=_aware(orm.created_at),
            available_at=_aware(orm.available_at),
            published_at=_aware(orm.published_at),
            attempt_count=orm.attempt_count,
            last_error=orm.last_error,
            status=orm.status,
            deduplication_key=orm.deduplication_key,
            claimed_by=orm.claimed_by,
            claim_token=orm.claim_token,
            claim_expires_at=_aware(orm.claim_expires_at),
        )
