"""Experience Store Repository (Async SQL) for Phase 8 (ban_ke_hoach_v1 §13 & §24)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.experience import Experience, ExperienceState
from windagent_storage.orm.experience_models import ExperienceRecordORM

logger = logging.getLogger("windagent.storage.repositories.experience")


class ExperienceRepository:
    """Durable async repository for storing and querying Experience instances."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: ExperienceRecordORM) -> Experience:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return Experience(
            experience_id=orm.id,
            execution_id=orm.execution_id,
            trajectory_id=orm.trajectory_id,
            parent_task_id=orm.parent_task_id,
            session_id=orm.session_id,
            project_id=orm.project_id,
            state=ExperienceState(orm.state),
            context=_parse_json(orm.context_json, {}),
            decision=_parse_json(orm.decision_json, {}),
            action=_parse_json(orm.action_json, {}),
            result=_parse_json(orm.result_json, {}),
            artifacts=_parse_json(orm.artifacts_json, []),
            metrics=_parse_json(orm.metrics_json, {}),
            evaluator_results=_parse_json(orm.evaluator_results_json, []),
            hypothesis=orm.hypothesis,
            confidence=float(orm.confidence),
            provenance=_parse_json(orm.provenance_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def save_experience(
        self,
        experience: Union[Experience, Dict[str, Any]],
    ) -> Experience:
        """Persists or updates an Experience record in the database."""
        if not isinstance(experience, Experience):
            experience = Experience.model_validate(experience)

        now = datetime.now(timezone.utc)
        context_json = json.dumps(experience.context, default=str)
        decision_json = json.dumps(experience.decision, default=str)
        action_json = json.dumps(experience.action, default=str)
        result_json = json.dumps(experience.result, default=str)
        artifacts_json = json.dumps(experience.artifacts, default=str)
        metrics_json = json.dumps(experience.metrics, default=str)
        evaluator_results_json = json.dumps(experience.evaluator_results, default=str)
        provenance_json = json.dumps(experience.provenance, default=str)

        existing = await self._session.get(ExperienceRecordORM, experience.experience_id)
        if not existing:
            orm = ExperienceRecordORM(
                id=experience.experience_id,
                execution_id=experience.execution_id,
                trajectory_id=experience.trajectory_id,
                parent_task_id=experience.parent_task_id,
                session_id=experience.session_id,
                project_id=experience.project_id,
                state=experience.state.value,
                context_json=context_json,
                decision_json=decision_json,
                action_json=action_json,
                result_json=result_json,
                artifacts_json=artifacts_json,
                metrics_json=metrics_json,
                evaluator_results_json=evaluator_results_json,
                hypothesis=experience.hypothesis,
                confidence=experience.confidence,
                provenance_json=provenance_json,
                created_at=experience.created_at or now,
                updated_at=experience.updated_at or now,
            )
            self._session.add(orm)
            await self._session.flush()
            return experience

        existing.execution_id = experience.execution_id
        existing.trajectory_id = experience.trajectory_id
        existing.parent_task_id = experience.parent_task_id
        existing.session_id = experience.session_id
        existing.project_id = experience.project_id
        existing.state = experience.state.value
        existing.context_json = context_json
        existing.decision_json = decision_json
        existing.action_json = action_json
        existing.result_json = result_json
        existing.artifacts_json = artifacts_json
        existing.metrics_json = metrics_json
        existing.evaluator_results_json = evaluator_results_json
        existing.hypothesis = experience.hypothesis
        existing.confidence = experience.confidence
        existing.provenance_json = provenance_json
        existing.updated_at = now
        await self._session.flush()
        return experience

    async def save_batch(
        self,
        experiences: Sequence[Union[Experience, Dict[str, Any]]],
    ) -> List[Experience]:
        """Persists a batch of Experience records within current transaction."""
        persisted = []
        for exp in experiences:
            saved = await self.save_experience(exp)
            persisted.append(saved)
        return persisted

    async def get_by_id(self, experience_id: str) -> Optional[Experience]:
        """Retrieves a single experience by identifier."""
        orm = await self._session.get(ExperienceRecordORM, experience_id)
        if not orm:
            return None
        return self._to_domain(orm)

    async def list_by_execution(self, execution_id: str) -> List[Experience]:
        """Lists experiences linked to a specific execution identifier."""
        stmt = (
            select(ExperienceRecordORM)
            .where(ExperienceRecordORM.execution_id == execution_id)
            .order_by(ExperienceRecordORM.created_at.desc())
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_trajectory(self, trajectory_id: str) -> List[Experience]:
        """Lists experiences linked to a specific trajectory identifier."""
        stmt = (
            select(ExperienceRecordORM)
            .where(ExperienceRecordORM.trajectory_id == trajectory_id)
            .order_by(ExperienceRecordORM.created_at.desc())
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_project(
        self,
        project_id: str,
        state: Optional[ExperienceState] = None,
    ) -> List[Experience]:
        """Lists experiences belonging to a project with optional state filter."""
        stmt = select(ExperienceRecordORM).where(ExperienceRecordORM.project_id == project_id)
        if state:
            stmt = stmt.where(ExperienceRecordORM.state == state.value)
        stmt = stmt.order_by(ExperienceRecordORM.created_at.desc())
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def list_by_state(
        self,
        state: ExperienceState,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Experience]:
        """Lists experiences by lifecycle state and minimum confidence score."""
        stmt = (
            select(ExperienceRecordORM)
            .where(ExperienceRecordORM.state == state.value)
            .where(ExperienceRecordORM.confidence >= min_confidence)
            .order_by(ExperienceRecordORM.confidence.desc(), ExperienceRecordORM.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]

    async def update_state(
        self,
        experience_id: str,
        new_state: ExperienceState,
        hypothesis: Optional[str] = None,
        confidence: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Experience]:
        """Updates the lifecycle state and diagnosis of an experience."""
        orm = await self._session.get(ExperienceRecordORM, experience_id)
        if not orm:
            return None

        orm.state = new_state.value
        if hypothesis is not None:
            orm.hypothesis = hypothesis
        if confidence is not None:
            orm.confidence = confidence
        if details:
            try:
                metrics_data = json.loads(orm.metrics_json or "{}")
            except Exception:
                metrics_data = {}
            metrics_data["diagnosis_details"] = details
            orm.metrics_json = json.dumps(metrics_data, default=str)

        orm.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._to_domain(orm)

    async def delete_experience(self, experience_id: str) -> bool:
        """Deletes an experience record from the database."""
        orm = await self._session.get(ExperienceRecordORM, experience_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True
