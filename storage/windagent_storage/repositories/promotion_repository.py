"""Promotion Decision Repository (Async SQL) for Phase 11 (ban_ke_hoach_v1 §17, §24, §35)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.promotion import (
    GateCheckResult,
    PromotionDecision,
    PromotionStatus,
)
from windagent_storage.orm.promotion_models import PromotionDecisionORM

logger = logging.getLogger("windagent.storage.repositories.promotion")


class PromotionRepository:
    """Durable async repository for storing and querying PromotionDecision records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: PromotionDecisionORM) -> PromotionDecision:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        gate_raw = _parse_json(orm.gate_checks_json, {})
        gate_checks = GateCheckResult(**gate_raw) if gate_raw else GateCheckResult()

        return PromotionDecision(
            decision_id=orm.id,
            candidate_id=orm.candidate_id,
            experiment_id=orm.experiment_id,
            source_harness_version=orm.source_harness_version,
            target_harness_version=orm.target_harness_version,
            status=PromotionStatus(orm.status),
            gate_checks=gate_checks,
            is_high_risk=bool(orm.is_high_risk),
            requires_human_approval=bool(orm.requires_human_approval),
            approved_by=orm.approved_by,
            approved_at=orm.approved_at,
            rejection_reason=orm.rejection_reason,
            decision_rationale=orm.decision_rationale,
            project_id=orm.project_id,
            domain=orm.domain,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _to_orm(self, dec: PromotionDecision) -> PromotionDecisionORM:
        return PromotionDecisionORM(
            id=dec.decision_id,
            candidate_id=dec.candidate_id,
            experiment_id=dec.experiment_id,
            source_harness_version=dec.source_harness_version,
            target_harness_version=dec.target_harness_version,
            status=dec.status.value,
            gate_checks_json=json.dumps(dec.gate_checks.model_dump()),
            is_high_risk=dec.is_high_risk,
            requires_human_approval=dec.requires_human_approval,
            approved_by=dec.approved_by,
            approved_at=dec.approved_at,
            rejection_reason=dec.rejection_reason,
            decision_rationale=dec.decision_rationale,
            project_id=dec.project_id,
            domain=dec.domain,
            metadata_json=json.dumps(dec.metadata),
            created_at=dec.created_at,
            updated_at=dec.updated_at,
        )

    async def get_decision(self, decision_id: str) -> Optional[PromotionDecision]:
        """Retrieves a promotion decision by ID."""
        stmt = select(PromotionDecisionORM).where(PromotionDecisionORM.id == decision_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def save_decision(self, decision: PromotionDecision) -> None:
        """Persists or updates a promotion decision."""
        decision.assert_invariants()
        stmt = select(PromotionDecisionORM).where(PromotionDecisionORM.id == decision.decision_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.target_harness_version = decision.target_harness_version
            existing.status = decision.status.value
            existing.gate_checks_json = json.dumps(decision.gate_checks.model_dump())
            existing.is_high_risk = decision.is_high_risk
            existing.requires_human_approval = decision.requires_human_approval
            existing.approved_by = decision.approved_by
            existing.approved_at = decision.approved_at
            existing.rejection_reason = decision.rejection_reason
            existing.decision_rationale = decision.decision_rationale
            existing.metadata_json = json.dumps(decision.metadata)
            existing.updated_at = decision.updated_at
        else:
            orm = self._to_orm(decision)
            self._session.add(orm)

        await self._session.flush()

    async def list_decisions(
        self,
        candidate_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[PromotionDecision]:
        """Lists promotion decisions matching query filters."""
        stmt = select(PromotionDecisionORM)
        if candidate_id:
            stmt = stmt.where(PromotionDecisionORM.candidate_id == candidate_id)
        if project_id:
            stmt = stmt.where(PromotionDecisionORM.project_id == project_id)
        if status:
            stmt = stmt.where(PromotionDecisionORM.status == status)

        stmt = stmt.order_by(PromotionDecisionORM.created_at.desc()).limit(limit)
        res = await self._session.execute(stmt)
        return [self._to_domain(orm) for orm in res.scalars().all()]

