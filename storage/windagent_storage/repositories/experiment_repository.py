"""Experiment Repository (Async SQL) for Phase 11 (ban_ke_hoach_v1 §17, §24)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.experiment import (
    Experiment,
    ExperimentMetrics,
    ExperimentStatus,
    ExperimentType,
    ExperimentVerdict,
    StatisticalComparison,
)
from windagent_storage.orm.experiment_models import ExperimentORM

logger = logging.getLogger("windagent.storage.repositories.experiment")


class ExperimentRepository:
    """Durable async repository for storing and querying Experiment records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: ExperimentORM) -> Experiment:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        base_metrics_raw = _parse_json(orm.baseline_metrics_json, None)
        base_metrics = ExperimentMetrics(**base_metrics_raw) if base_metrics_raw else None

        cand_metrics_raw = _parse_json(orm.candidate_metrics_json, None)
        cand_metrics = ExperimentMetrics(**cand_metrics_raw) if cand_metrics_raw else None

        comp_raw = _parse_json(orm.comparison_json, None)
        comparison = StatisticalComparison(**comp_raw) if comp_raw else None

        return Experiment(
            experiment_id=orm.id,
            candidate_id=orm.candidate_id,
            baseline_harness_version=orm.baseline_harness_version,
            experiment_type=ExperimentType(orm.experiment_type),
            status=ExperimentStatus(orm.status),
            dataset_id=orm.dataset_id,
            sample_size=orm.sample_size,
            baseline_metrics=base_metrics,
            candidate_metrics=cand_metrics,
            comparison=comparison,
            safety_check_passed=bool(orm.safety_check_passed),
            reliability_check_passed=bool(orm.reliability_check_passed),
            verdict=ExperimentVerdict(orm.verdict),
            project_id=orm.project_id,
            domain=orm.domain,
            created_by=orm.created_by,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            completed_at=orm.completed_at,
        )

    def _to_orm(self, exp: Experiment) -> ExperimentORM:
        return ExperimentORM(
            id=exp.experiment_id,
            candidate_id=exp.candidate_id,
            baseline_harness_version=exp.baseline_harness_version,
            experiment_type=exp.experiment_type.value,
            status=exp.status.value,
            dataset_id=exp.dataset_id,
            sample_size=exp.sample_size,
            baseline_metrics_json=json.dumps(exp.baseline_metrics.model_dump() if exp.baseline_metrics else {}),
            candidate_metrics_json=json.dumps(exp.candidate_metrics.model_dump() if exp.candidate_metrics else {}),
            comparison_json=json.dumps(exp.comparison.model_dump() if exp.comparison else {}),
            safety_check_passed=exp.safety_check_passed,
            reliability_check_passed=exp.reliability_check_passed,
            verdict=exp.verdict.value,
            project_id=exp.project_id,
            domain=exp.domain,
            created_by=exp.created_by,
            metadata_json=json.dumps(exp.metadata),
            created_at=exp.created_at,
            updated_at=exp.updated_at,
            completed_at=exp.completed_at,
        )

    async def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Retrieves an experiment by ID."""
        stmt = select(ExperimentORM).where(ExperimentORM.id == experiment_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def save_experiment(self, experiment: Experiment) -> None:
        """Persists or updates an experiment record."""
        experiment.assert_invariants()
        stmt = select(ExperimentORM).where(ExperimentORM.id == experiment.experiment_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.status = experiment.status.value
            existing.sample_size = experiment.sample_size
            existing.baseline_metrics_json = json.dumps(
                experiment.baseline_metrics.model_dump() if experiment.baseline_metrics else {}
            )
            existing.candidate_metrics_json = json.dumps(
                experiment.candidate_metrics.model_dump() if experiment.candidate_metrics else {}
            )
            existing.comparison_json = json.dumps(
                experiment.comparison.model_dump() if experiment.comparison else {}
            )
            existing.safety_check_passed = experiment.safety_check_passed
            existing.reliability_check_passed = experiment.reliability_check_passed
            existing.verdict = experiment.verdict.value
            existing.metadata_json = json.dumps(experiment.metadata)
            existing.updated_at = experiment.updated_at
            existing.completed_at = experiment.completed_at
        else:
            orm = self._to_orm(experiment)
            self._session.add(orm)

        await self._session.flush()

    async def list_experiments(
        self,
        candidate_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Experiment]:
        """Lists experiments matching query filters."""
        stmt = select(ExperimentORM)
        if candidate_id:
            stmt = stmt.where(ExperimentORM.candidate_id == candidate_id)
        if project_id:
            stmt = stmt.where(ExperimentORM.project_id == project_id)
        if status:
            stmt = stmt.where(ExperimentORM.status == status)

        stmt = stmt.order_by(ExperimentORM.created_at.desc()).limit(limit)
        res = await self._session.execute(stmt)
        return [self._to_domain(orm) for orm in res.scalars().all()]

