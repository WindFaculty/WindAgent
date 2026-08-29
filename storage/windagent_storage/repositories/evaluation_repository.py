"""Evaluation Engine V2 Repository (Async SQL) for Phase 7 (ban_ke_hoach_v1 §12)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.evaluation import EvaluationDimension, EvaluationRecord
from windagent_storage.orm.evaluation_models import EvaluationRecordORM

logger = logging.getLogger("windagent.storage.repositories.evaluation")


class EvaluationRepository:
    """Durable async repository for storing and querying EvaluationRecord instances."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: EvaluationRecordORM) -> EvaluationRecord:
        try:
            evidence_refs = json.loads(orm.evidence_refs_json or "[]")
        except Exception:
            evidence_refs = []
        try:
            details = json.loads(orm.details_json or "{}")
        except Exception:
            details = {}

        return EvaluationRecord(
            evaluation_id=orm.id,
            execution_id=orm.execution_id,
            trajectory_id=orm.trajectory_id,
            evaluator_version=orm.evaluator_version,
            harness_version=orm.harness_version,
            dimension=EvaluationDimension(orm.dimension),
            metric_name=orm.metric_name,
            score=float(orm.score),
            threshold=float(orm.threshold),
            confidence=float(orm.confidence),
            evidence_refs=evidence_refs,
            passed=bool(orm.passed),
            blocked=bool(orm.blocked),
            details=details,
            created_at=orm.created_at,
        )

    async def save_record(
        self,
        record: Union[EvaluationRecord, Dict[str, Any]],
    ) -> EvaluationRecord:
        """Persists or updates an EvaluationRecord in the database."""
        if not isinstance(record, EvaluationRecord):
            record = EvaluationRecord.model_validate(record)

        now = datetime.now(timezone.utc)
        evidence_json = json.dumps(record.evidence_refs)
        details_json = json.dumps(record.details, default=str)

        existing = await self._session.get(EvaluationRecordORM, record.evaluation_id)
        if not existing:
            orm = EvaluationRecordORM(
                id=record.evaluation_id,
                execution_id=record.execution_id,
                trajectory_id=record.trajectory_id,
                evaluator_version=record.evaluator_version,
                harness_version=record.harness_version,
                dimension=record.dimension.value,
                metric_name=record.metric_name,
                score=record.score,
                threshold=record.threshold,
                confidence=record.confidence,
                evidence_refs_json=evidence_json,
                passed=record.passed,
                blocked=record.blocked,
                details_json=details_json,
                created_at=record.created_at or now,
            )
            self._session.add(orm)
            await self._session.flush()
            return record

        existing.execution_id = record.execution_id
        existing.trajectory_id = record.trajectory_id
        existing.evaluator_version = record.evaluator_version
        existing.harness_version = record.harness_version
        existing.dimension = record.dimension.value
        existing.metric_name = record.metric_name
        existing.score = record.score
        existing.threshold = record.threshold
        existing.confidence = record.confidence
        existing.evidence_refs_json = evidence_json
        existing.passed = record.passed
        existing.blocked = record.blocked
        existing.details_json = details_json
        await self._session.flush()
        return record

    async def save_batch(
        self,
        records: Sequence[Union[EvaluationRecord, Dict[str, Any]]],
    ) -> List[EvaluationRecord]:
        """Persists a batch of EvaluationRecords within the current transaction."""
        persisted = []
        for r in records:
            saved = await self.save_record(r)
            persisted.append(saved)
        return persisted

    async def get_by_id(self, evaluation_id: str) -> Optional[EvaluationRecord]:
        """Retrieves a single evaluation record by its identifier."""
        orm = await self._session.get(EvaluationRecordORM, evaluation_id)
        if not orm:
            return None
        return self._to_domain(orm)

    async def list_by_execution(self, execution_id: str) -> List[EvaluationRecord]:
        """Lists all evaluation records for an execution."""
        stmt = (
            select(EvaluationRecordORM)
            .where(EvaluationRecordORM.execution_id == execution_id)
            .order_by(EvaluationRecordORM.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_trajectory(self, trajectory_id: str) -> List[EvaluationRecord]:
        """Lists all evaluation records associated with a trajectory."""
        stmt = (
            select(EvaluationRecordORM)
            .where(EvaluationRecordORM.trajectory_id == trajectory_id)
            .order_by(EvaluationRecordORM.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_harness(
        self,
        harness_version: str,
        limit: int = 200,
    ) -> List[EvaluationRecord]:
        """Lists evaluation records recorded under a specific harness version."""
        stmt = (
            select(EvaluationRecordORM)
            .where(EvaluationRecordORM.harness_version == harness_version)
            .order_by(EvaluationRecordORM.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_dimension(
        self,
        dimension: Union[EvaluationDimension, str],
        limit: int = 100,
    ) -> List[EvaluationRecord]:
        """Lists evaluation records filtered by dimension."""
        dim_str = dimension.value if isinstance(dimension, EvaluationDimension) else str(dimension)
        stmt = (
            select(EvaluationRecordORM)
            .where(EvaluationRecordORM.dimension == dim_str)
            .order_by(EvaluationRecordORM.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def get_baseline_scores(
        self,
        evaluator_version: Optional[str] = None,
        harness_version: Optional[str] = None,
    ) -> Dict[str, float]:
        """Calculates mean scores per metric_name for non-blocked evaluations.

        Used as production baseline authority for candidate comparisons.
        """
        stmt = (
            select(
                EvaluationRecordORM.metric_name,
                func.avg(EvaluationRecordORM.score).label("avg_score"),
            )
            .where(EvaluationRecordORM.blocked.is_(False))
            .group_by(EvaluationRecordORM.metric_name)
        )
        if evaluator_version:
            stmt = stmt.where(EvaluationRecordORM.evaluator_version == evaluator_version)
        if harness_version:
            stmt = stmt.where(EvaluationRecordORM.harness_version == harness_version)

        res = await self._session.execute(stmt)
        return {str(row[0]): float(row[1]) for row in res.all()}

    async def delete_by_execution(self, execution_id: str) -> int:
        """Deletes all evaluation records for an execution."""
        stmt = delete(EvaluationRecordORM).where(
            EvaluationRecordORM.execution_id == execution_id
        )
        res = await self._session.execute(stmt)
        return int(res.rowcount or 0)

