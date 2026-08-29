"""Skill Evolution Repository (Async SQL) for Phase 12 (ban_ke_hoach_v1 §18, §24, §25)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillEvaluationResult,
    SkillPromotionDecision,
    SkillPromotionStatus,
    SkillRiskLevel,
    SkillSecurityAuditResult,
    SkillVersion,
    SkillVersionStatus,
)
from windagent_storage.orm.skill_evolution_models import (
    SkillCandidateORM,
    SkillPromotionDecisionORM,
    SkillVersionORM,
)

logger = logging.getLogger("windagent.storage.repositories.skill_evolution")


def _parse_json(val: Optional[str], default: Any) -> Any:
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


class SkillEvolutionRepository:
    """Async SQL repository implementing SkillEvolutionRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -------------------------------------------------------------------------
    # Candidate operations
    # -------------------------------------------------------------------------

    def _candidate_to_domain(self, orm: SkillCandidateORM) -> SkillCandidate:
        audit_raw = _parse_json(orm.security_audit_json, None)
        audit = SkillSecurityAuditResult(**audit_raw) if audit_raw else None

        eval_raw = _parse_json(orm.evaluation_json, None)
        evaluation = SkillEvaluationResult(**eval_raw) if eval_raw else None

        return SkillCandidate(
            candidate_id=orm.id,
            skill_id=orm.skill_id,
            proposed_manifest=_parse_json(orm.proposed_manifest_json, {}),
            proposed_code=orm.proposed_code,
            reasoning_summary=orm.reasoning_summary,
            supporting_experiences=_parse_json(orm.supporting_experiences_json, []),
            status=SkillCandidateStatus(orm.status),
            risk_level=SkillRiskLevel(orm.risk_level),
            is_executable=bool(orm.is_executable),
            is_high_risk=bool(orm.is_high_risk),
            security_audit=audit,
            evaluation=evaluation,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _candidate_to_orm(self, cand: SkillCandidate) -> SkillCandidateORM:
        return SkillCandidateORM(
            id=cand.candidate_id,
            skill_id=cand.skill_id,
            status=cand.status.value,
            risk_level=cand.risk_level.value,
            is_executable=cand.is_executable,
            is_high_risk=cand.is_high_risk,
            proposed_manifest_json=json.dumps(cand.proposed_manifest),
            proposed_code=cand.proposed_code,
            reasoning_summary=cand.reasoning_summary,
            supporting_experiences_json=json.dumps(cand.supporting_experiences),
            security_audit_json=json.dumps(cand.security_audit.model_dump()) if cand.security_audit else None,
            evaluation_json=json.dumps(cand.evaluation.model_dump()) if cand.evaluation else None,
            metadata_json=json.dumps(cand.metadata),
            created_at=cand.created_at,
            updated_at=cand.updated_at,
        )

    async def get_candidate(self, candidate_id: str) -> Optional[SkillCandidate]:
        stmt = select(SkillCandidateORM).where(SkillCandidateORM.id == candidate_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._candidate_to_domain(orm) if orm else None

    async def save_candidate(self, candidate: SkillCandidate) -> None:
        stmt = select(SkillCandidateORM).where(SkillCandidateORM.id == candidate.candidate_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.status = candidate.status.value
            existing.risk_level = candidate.risk_level.value
            existing.is_executable = candidate.is_executable
            existing.is_high_risk = candidate.is_high_risk
            existing.proposed_manifest_json = json.dumps(candidate.proposed_manifest)
            existing.proposed_code = candidate.proposed_code
            existing.reasoning_summary = candidate.reasoning_summary
            existing.supporting_experiences_json = json.dumps(candidate.supporting_experiences)
            existing.security_audit_json = (
                json.dumps(candidate.security_audit.model_dump()) if candidate.security_audit else None
            )
            existing.evaluation_json = (
                json.dumps(candidate.evaluation.model_dump()) if candidate.evaluation else None
            )
            existing.metadata_json = json.dumps(candidate.metadata)
            existing.updated_at = candidate.updated_at
        else:
            self._session.add(self._candidate_to_orm(candidate))

        await self._session.flush()

    async def list_candidates(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillCandidate]:
        stmt = select(SkillCandidateORM)
        if skill_id:
            stmt = stmt.where(SkillCandidateORM.skill_id == skill_id)
        if status:
            stmt = stmt.where(SkillCandidateORM.status == status)
        stmt = stmt.order_by(desc(SkillCandidateORM.created_at)).limit(limit)

        res = await self._session.execute(stmt)
        return [self._candidate_to_domain(r) for r in res.scalars().all()]

    # -------------------------------------------------------------------------
    # Version operations
    # -------------------------------------------------------------------------

    def _version_to_domain(self, orm: SkillVersionORM) -> SkillVersion:
        return SkillVersion(
            version_id=orm.id,
            skill_id=orm.skill_id,
            version=orm.version,
            parent_version=orm.parent_version,
            manifest=_parse_json(orm.manifest_json, {}),
            code_hash=orm.code_hash,
            source_code=orm.source_code,
            status=SkillVersionStatus(orm.status),
            promoted_from_candidate_id=orm.promoted_from_candidate_id,
            security_audit_id=orm.security_audit_id,
            evaluation_id=orm.evaluation_id,
            created_at=orm.created_at,
            activated_at=orm.activated_at,
            deprecated_at=orm.deprecated_at,
        )

    def _version_to_orm(self, ver: SkillVersion) -> SkillVersionORM:
        return SkillVersionORM(
            id=ver.version_id,
            skill_id=ver.skill_id,
            version=ver.version,
            parent_version=ver.parent_version,
            manifest_json=json.dumps(ver.manifest),
            code_hash=ver.code_hash,
            source_code=ver.source_code,
            status=ver.status.value,
            promoted_from_candidate_id=ver.promoted_from_candidate_id,
            security_audit_id=ver.security_audit_id,
            evaluation_id=ver.evaluation_id,
            created_at=ver.created_at,
            activated_at=ver.activated_at,
            deprecated_at=ver.deprecated_at,
        )

    async def get_version(self, version_id: str) -> Optional[SkillVersion]:
        stmt = select(SkillVersionORM).where(SkillVersionORM.id == version_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._version_to_domain(orm) if orm else None

    async def get_version_by_semver(self, skill_id: str, version: str) -> Optional[SkillVersion]:
        stmt = select(SkillVersionORM).where(
            SkillVersionORM.skill_id == skill_id,
            SkillVersionORM.version == version,
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._version_to_domain(orm) if orm else None

    async def get_active_version(self, skill_id: str) -> Optional[SkillVersion]:
        stmt = select(SkillVersionORM).where(
            SkillVersionORM.skill_id == skill_id,
            SkillVersionORM.status == SkillVersionStatus.ACTIVE.value,
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._version_to_domain(orm) if orm else None

    async def save_version(self, version: SkillVersion) -> None:
        stmt = select(SkillVersionORM).where(SkillVersionORM.id == version.version_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.status = version.status.value
            existing.manifest_json = json.dumps(version.manifest)
            existing.code_hash = version.code_hash
            existing.source_code = version.source_code
            existing.activated_at = version.activated_at
            existing.deprecated_at = version.deprecated_at
        else:
            self._session.add(self._version_to_orm(version))

        await self._session.flush()

    async def list_versions(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillVersion]:
        stmt = select(SkillVersionORM)
        if skill_id:
            stmt = stmt.where(SkillVersionORM.skill_id == skill_id)
        if status:
            stmt = stmt.where(SkillVersionORM.status == status)
        stmt = stmt.order_by(desc(SkillVersionORM.created_at)).limit(limit)

        res = await self._session.execute(stmt)
        return [self._version_to_domain(r) for r in res.scalars().all()]

    # -------------------------------------------------------------------------
    # Promotion operations
    # -------------------------------------------------------------------------

    def _promotion_to_domain(self, orm: SkillPromotionDecisionORM) -> SkillPromotionDecision:
        return SkillPromotionDecision(
            decision_id=orm.id,
            candidate_id=orm.candidate_id,
            skill_id=orm.skill_id,
            source_version=orm.source_version,
            target_version=orm.target_version,
            status=SkillPromotionStatus(orm.status),
            security_audit_passed=bool(orm.security_audit_passed),
            evaluation_passed=bool(orm.evaluation_passed),
            requires_human_approval=bool(orm.requires_human_approval),
            approved_by=orm.approved_by,
            approved_at=orm.approved_at,
            rejection_reason=orm.rejection_reason,
            decision_rationale=orm.decision_rationale,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _promotion_to_orm(self, dec: SkillPromotionDecision) -> SkillPromotionDecisionORM:
        return SkillPromotionDecisionORM(
            id=dec.decision_id,
            candidate_id=dec.candidate_id,
            skill_id=dec.skill_id,
            source_version=dec.source_version,
            target_version=dec.target_version,
            status=dec.status.value,
            security_audit_passed=dec.security_audit_passed,
            evaluation_passed=dec.evaluation_passed,
            requires_human_approval=dec.requires_human_approval,
            approved_by=dec.approved_by,
            approved_at=dec.approved_at,
            rejection_reason=dec.rejection_reason,
            decision_rationale=dec.decision_rationale,
            created_at=dec.created_at,
            updated_at=dec.updated_at,
        )

    async def get_promotion(self, decision_id: str) -> Optional[SkillPromotionDecision]:
        stmt = select(SkillPromotionDecisionORM).where(SkillPromotionDecisionORM.id == decision_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._promotion_to_domain(orm) if orm else None

    async def save_promotion(self, decision: SkillPromotionDecision) -> None:
        stmt = select(SkillPromotionDecisionORM).where(SkillPromotionDecisionORM.id == decision.decision_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.status = decision.status.value
            existing.security_audit_passed = decision.security_audit_passed
            existing.evaluation_passed = decision.evaluation_passed
            existing.approved_by = decision.approved_by
            existing.approved_at = decision.approved_at
            existing.rejection_reason = decision.rejection_reason
            existing.decision_rationale = decision.decision_rationale
            existing.updated_at = decision.updated_at
        else:
            self._session.add(self._promotion_to_orm(decision))

        await self._session.flush()

    async def list_promotions(
        self,
        skill_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillPromotionDecision]:
        stmt = select(SkillPromotionDecisionORM)
        if skill_id:
            stmt = stmt.where(SkillPromotionDecisionORM.skill_id == skill_id)
        if candidate_id:
            stmt = stmt.where(SkillPromotionDecisionORM.candidate_id == candidate_id)
        if status:
            stmt = stmt.where(SkillPromotionDecisionORM.status == status)
        stmt = stmt.order_by(desc(SkillPromotionDecisionORM.created_at)).limit(limit)

        res = await self._session.execute(stmt)
        return [self._promotion_to_domain(r) for r in res.scalars().all()]


__all__ = ["SkillEvolutionRepository"]

