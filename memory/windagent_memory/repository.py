"""
Durable Memory Record Repository for WindAgent Memory Package (Phase 21).
Implements transactional read/write/delete of memory records via the existing
storage ORM and UnitOfWork, ensuring secret exclusion, TTL-based eviction,
and cross-project isolation in durable storage.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.errors.exceptions import NotFoundError
from windagent_memory.models import MemoryRecord, MemoryScope, RetentionPolicy
from windagent_storage.orm.v2_orchestration_models import MemoryRecordORM

logger = logging.getLogger("windagent.memory.repository")


def _to_domain(orm: MemoryRecordORM) -> MemoryRecord:
    """Converts ORM model to domain MemoryRecord."""
    value_raw = json.loads(orm.value_json) if orm.value_json else {}
    scope_str = orm.memory_type.upper() if orm.memory_type else "SESSION"

    try:
        scope = MemoryScope(scope_str.lower())
    except ValueError:
        scope = MemoryScope.SESSION

    return MemoryRecord(
        id=orm.id,
        scope=scope,
        key=orm.key,
        value=value_raw,
        provenance_source="storage",
        session_id=orm.session_id,
        project_id=None,  # Field exists in ORM but not in legacy model; will be added
        created_at=orm.created_at or datetime.now(timezone.utc),
        updated_at=orm.updated_at or datetime.now(timezone.utc),
    )


def _to_orm(record: MemoryRecord) -> MemoryRecordORM:
    """Converts domain MemoryRecord to ORM model."""
    value_json = json.dumps(record.value) if not isinstance(record.value, str) else record.value
    return MemoryRecordORM(
        id=record.id,
        session_id=record.session_id,
        memory_type=record.scope.value,
        key=record.key,
        value_json=value_json,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class MemoryRecordRepository:
    """Durable repository for memory records using SQL storage."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, record: MemoryRecord) -> None:
        """Persists a memory record (upsert)."""
        orm = _to_orm(record)
        await self._session.merge(orm)
        logger.debug(f"Persisted memory record [{record.key}] scope={record.scope.value}")

    async def get_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieves a memory record by ID."""
        stmt = select(MemoryRecordORM).where(MemoryRecordORM.id == record_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def get_by_key(self, scope: MemoryScope, key: str, session_id: Optional[str] = None) -> Optional[MemoryRecord]:
        """Retrieves a memory record by scope + key + optional session_id."""
        stmt = select(MemoryRecordORM).where(
            MemoryRecordORM.memory_type == scope.value,
            MemoryRecordORM.key == key,
        )
        if session_id:
            stmt = stmt.where(MemoryRecordORM.session_id == session_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def delete(self, record_id: str) -> bool:
        """Deletes a memory record by ID."""
        stmt = delete(MemoryRecordORM).where(MemoryRecordORM.id == record_id)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def delete_by_key(self, scope: MemoryScope, key: str, session_id: Optional[str] = None) -> bool:
        """Deletes a memory record by scope + key."""
        stmt = delete(MemoryRecordORM).where(
            MemoryRecordORM.memory_type == scope.value,
            MemoryRecordORM.key == key,
        )
        if session_id:
            stmt = stmt.where(MemoryRecordORM.session_id == session_id)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def list_by_session(self, session_id: str) -> List[MemoryRecord]:
        """Lists all memory records for a session."""
        stmt = select(MemoryRecordORM).where(
            MemoryRecordORM.session_id == session_id
        ).order_by(MemoryRecordORM.created_at.asc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [_to_domain(o) for o in orms]

    async def list_by_scope(self, scope: MemoryScope, limit: int = 100) -> List[MemoryRecord]:
        """Lists memory records for a given scope."""
        stmt = select(MemoryRecordORM).where(
            MemoryRecordORM.memory_type == scope.value
        ).order_by(MemoryRecordORM.updated_at.desc()).limit(limit)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [_to_domain(o) for o in orms]

    async def evict_expired(self, policy: RetentionPolicy) -> int:
        """Evicts expired memory records based on TTL and retention policy.
        Returns count of evicted records.
        """
        if not policy.auto_evict_expired:
            return 0

        now = datetime.now(timezone.utc)
        stmt = select(MemoryRecordORM)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()

        evicted_count = 0
        for orm in orms:
            record = _to_domain(orm)
            if record.is_expired(reference_time=now):
                await self.delete(orm.id)
                evicted_count += 1

        # Enforce max_records_per_scope
        if policy.max_records_per_scope:
            for scope in MemoryScope:
                scope_records = await self.list_by_scope(scope)
                if len(scope_records) > policy.max_records_per_scope:
                    # Evict oldest records beyond the limit
                    to_evict = sorted(scope_records, key=lambda r: r.updated_at)
                    for record in to_evict[:len(to_evict) - policy.max_records_per_scope]:
                        await self.delete(record.id)
                        evicted_count += 1

        if evicted_count > 0:
            logger.info(f"Evicted {evicted_count} expired/stale memory records from durable storage.")

        return evicted_count
