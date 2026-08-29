"""Memory V2 Repository (Async SQL / CAS guarded) for Phase 6."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession


from windagent_core.domain.memory_v2 import (
    LearningMetadata,
    MemoryRecordV2,
    MemoryScope,
    ValidationStatus,
)
from windagent_storage.orm.memory_v2_models import MemoryRecordV2ORM


logger = logging.getLogger("windagent.storage.repositories.memory_v2")


class MemoryV2Repository:
    """Durable async repository for Memory V2 records with CAS versioning."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: MemoryRecordV2ORM) -> MemoryRecordV2:
        try:
            value = json.loads(orm.value_json)
        except Exception:
            value = orm.value_json
        try:
            tags = json.loads(orm.tags_json or "{}")
        except Exception:
            tags = {}
        try:
            evidence_refs = json.loads(orm.evidence_refs_json or "[]")
        except Exception:
            evidence_refs = []
        try:
            source_run_ids = json.loads(orm.source_run_ids_json or "[]")
        except Exception:
            source_run_ids = []

        learning_meta = LearningMetadata(
            evidence_refs=evidence_refs,
            confidence=float(orm.confidence or 0.0),
            sample_size=int(orm.sample_size or 0),
            source_run_ids=source_run_ids,
            harness_version=orm.harness_version,
            validation_status=ValidationStatus(orm.validation_status),
            last_validated_at=orm.last_validated_at,
            supersedes_id=orm.supersedes_id,
        )

        return MemoryRecordV2(
            id=orm.id,
            scope=MemoryScope(orm.scope),
            key=orm.key,
            value=value,
            provenance_source=orm.provenance_source,
            project_id=orm.project_id,
            session_id=orm.session_id,
            tags=tags,
            ttl_seconds=orm.ttl_seconds,
            content_hash=orm.content_hash,
            learning_metadata=learning_meta,
            version=orm.version,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def save_record(
        self,
        record: Union[MemoryRecordV2, Dict[str, Any]],
        expected_version: Optional[int] = None,
    ) -> Optional[MemoryRecordV2]:
        """Saves or updates a MemoryRecordV2. If expected_version is specified, performs CAS."""
        if not isinstance(record, MemoryRecordV2):
            record = MemoryRecordV2.model_validate(record)

        now = datetime.now(timezone.utc)
        value_json = json.dumps(record.value, default=str)
        tags_json = json.dumps(record.tags)
        evidence_json = json.dumps(record.learning_metadata.evidence_refs)
        sources_json = json.dumps(record.learning_metadata.source_run_ids)
        content_hash = record.ensure_hash()

        # Check if exists by ID first, then by (scope, key, project, session)
        existing = await self._session.get(MemoryRecordV2ORM, record.id)
        if not existing:
            stmt = select(MemoryRecordV2ORM).where(
                MemoryRecordV2ORM.scope == record.scope.value,
                MemoryRecordV2ORM.key == record.key,
                MemoryRecordV2ORM.project_id == record.project_id,
                MemoryRecordV2ORM.session_id == record.session_id,
            )
            res = await self._session.execute(stmt)
            existing = res.scalar_one_or_none()

        if existing:
            if expected_version is not None and existing.version != expected_version:
                logger.warning(
                    f"CAS version conflict on memory record [{record.id}]: "
                    f"expected {expected_version}, found {existing.version}"
                )
                return None

            existing.value_json = value_json
            existing.provenance_source = record.provenance_source
            existing.project_id = record.project_id
            existing.session_id = record.session_id
            existing.tags_json = tags_json
            existing.ttl_seconds = record.ttl_seconds
            existing.content_hash = content_hash
            existing.evidence_refs_json = evidence_json
            existing.confidence = record.learning_metadata.confidence
            existing.sample_size = record.learning_metadata.sample_size
            existing.source_run_ids_json = sources_json
            existing.harness_version = record.learning_metadata.harness_version
            existing.validation_status = record.learning_metadata.validation_status.value
            existing.last_validated_at = record.learning_metadata.last_validated_at
            existing.supersedes_id = record.learning_metadata.supersedes_id
            existing.version += 1
            existing.updated_at = now
            await self._session.flush()
            return self._to_domain(existing)

        orm = MemoryRecordV2ORM(
            id=record.id,
            scope=record.scope.value,
            key=record.key,
            value_json=value_json,
            provenance_source=record.provenance_source,
            project_id=record.project_id,
            session_id=record.session_id,
            tags_json=tags_json,
            ttl_seconds=record.ttl_seconds,
            content_hash=content_hash,
            evidence_refs_json=evidence_json,
            confidence=record.learning_metadata.confidence,
            sample_size=record.learning_metadata.sample_size,
            source_run_ids_json=sources_json,
            harness_version=record.learning_metadata.harness_version,
            validation_status=record.learning_metadata.validation_status.value,
            last_validated_at=record.learning_metadata.last_validated_at,
            supersedes_id=record.learning_metadata.supersedes_id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(orm)
        await self._session.flush()
        return self._to_domain(orm)

    async def get_by_id(self, record_id: str) -> Optional[MemoryRecordV2]:
        orm = await self._session.get(MemoryRecordV2ORM, record_id)
        if not orm:
            return None
        rec = self._to_domain(orm)
        if rec.is_expired():
            await self.delete_record(record_id)
            return None
        return rec

    async def get_by_key(
        self,
        scope: str,
        key: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[MemoryRecordV2]:
        stmt = select(MemoryRecordV2ORM).where(
            MemoryRecordV2ORM.scope == scope,
            MemoryRecordV2ORM.key == key,
            MemoryRecordV2ORM.project_id == project_id,
            MemoryRecordV2ORM.session_id == session_id,
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        rec = self._to_domain(orm)
        if rec.is_expired():
            await self.delete_record(orm.id)
            return None
        return rec

    async def list_records(
        self,
        scope: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        validation_status: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100,
    ) -> List[MemoryRecordV2]:
        stmt = select(MemoryRecordV2ORM).order_by(MemoryRecordV2ORM.updated_at.desc())
        if scope:
            stmt = stmt.where(MemoryRecordV2ORM.scope == scope)
        if project_id:
            stmt = stmt.where(MemoryRecordV2ORM.project_id == project_id)
        if session_id:
            stmt = stmt.where(MemoryRecordV2ORM.session_id == session_id)
        if validation_status:
            stmt = stmt.where(MemoryRecordV2ORM.validation_status == validation_status)
        if min_confidence is not None:
            stmt = stmt.where(MemoryRecordV2ORM.confidence >= min_confidence)
        stmt = stmt.limit(limit)

        res = await self._session.execute(stmt)
        orms_list = res.scalars().all()
        results = []
        now = datetime.now(timezone.utc)
        for orm in orms_list:
            rec = self._to_domain(orm)
            if rec.is_expired(reference_time=now):
                await self.delete_record(orm.id)
            else:
                results.append(rec)
        return results

    async def supersede_record(self, old_id: str, new_id: str) -> bool:
        orm = await self._session.get(MemoryRecordV2ORM, old_id)
        if not orm:
            return False
        orm.validation_status = ValidationStatus.SUPERSEDED.value
        orm.supersedes_id = new_id
        orm.updated_at = datetime.now(timezone.utc)
        orm.version += 1
        await self._session.flush()
        return True

    async def delete_record(self, record_id: str) -> bool:
        orm = await self._session.get(MemoryRecordV2ORM, record_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    async def delete_by_key(
        self,
        scope: str,
        key: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        stmt = delete(MemoryRecordV2ORM).where(
            MemoryRecordV2ORM.scope == scope,
            MemoryRecordV2ORM.key == key,
            MemoryRecordV2ORM.project_id == project_id,
            MemoryRecordV2ORM.session_id == session_id,
        )
        res = await self._session.execute(stmt)
        await self._session.flush()
        return res.rowcount > 0

    async def evict_expired(self) -> int:
        list_stmt = select(MemoryRecordV2ORM).filter(MemoryRecordV2ORM.ttl_seconds.isnot(None))
        res = await self._session.execute(list_stmt)
        orms = res.scalars().all()
        now = datetime.now(timezone.utc)
        expired_ids = []
        for orm in orms:
            rec = self._to_domain(orm)
            if rec.is_expired(reference_time=now):
                expired_ids.append(orm.id)
        if expired_ids:
            del_stmt = delete(MemoryRecordV2ORM).where(MemoryRecordV2ORM.id.in_(expired_ids))
            await self._session.execute(del_stmt)
            await self._session.flush()
        return len(expired_ids)

    async def count_by_scope(self) -> Dict[str, int]:
        stmt = select(MemoryRecordV2ORM.scope, func.count(MemoryRecordV2ORM.id)).group_by(MemoryRecordV2ORM.scope)
        res = await self._session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}
