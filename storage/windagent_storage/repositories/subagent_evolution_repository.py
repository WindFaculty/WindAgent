"""Subagent Evolution Repository (Async SQL) for Phase 13 (ban_ke_hoach_v1 §19, §24, §25)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.agent_loop import AgentBudgetLimits
from windagent_core.domain.subagent_evolution import (
    MemoryAccessPolicy,
    ModelRoutingPolicy,
    SubagentCandidate,
    SubagentCandidateStatus,
    SubagentEvaluationResult,
    SubagentOutputContract,
    SubagentPromotionDecision,
    SubagentPromotionStatus,
    SubagentRiskLevel,
    SubagentSecurityAuditResult,
    SubagentSpecStatus,
    SubagentSpecVersion,
)
from windagent_storage.orm.subagent_evolution_models import (
    SubagentCandidateORM,
    SubagentPromotionDecisionORM,
    SubagentSpecVersionORM,
)

logger = logging.getLogger("windagent.storage.repositories.subagent_evolution")


def _parse_json(val: Optional[str], default: Any) -> Any:
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


class SubagentEvolutionRepository:
    """Async SQL repository implementing SubagentEvolutionRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -------------------------------------------------------------------------
    # Candidate operations
    # -------------------------------------------------------------------------

    def _candidate_to_domain(self, orm: SubagentCandidateORM) -> SubagentCandidate:
        audit_raw = _parse_json(orm.security_audit_json, None)
        audit = SubagentSecurityAuditResult(**audit_raw) if audit_raw else None

        eval_raw = _parse_json(orm.evaluation_json, None)
        evaluation = SubagentEvaluationResult(**eval_raw) if eval_raw else None

        return SubagentCandidate(
            candidate_id=orm.id,
            role=orm.role,
            proposed_spec=_parse_json(orm.proposed_spec_json, {}),
            reasoning_summary=orm.reasoning_summary,
            supporting_experiences=_parse_json(orm.supporting_experiences_json, []),
            status=SubagentCandidateStatus(orm.status),
            risk_level=SubagentRiskLevel(orm.risk_level),
            is_high_risk=bool(orm.is_high_risk),
            security_audit=audit,
            evaluation=evaluation,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _candidate_to_orm(self, cand: SubagentCandidate) -> SubagentCandidateORM:
        return SubagentCandidateORM(
            id=cand.candidate_id,
            role=cand.role,
            status=cand.status.value,
            risk_level=cand.risk_level.value,
            is_high_risk=cand.is_high_risk,
            proposed_spec_json=json.dumps(cand.proposed_spec, default=str),
            reasoning_summary=cand.reasoning_summary,
            supporting_experiences_json=json.dumps(cand.supporting_experiences),
            security_audit_json=json.dumps(cand.security_audit.model_dump(), default=str) if cand.security_audit else None,
            evaluation_json=json.dumps(cand.evaluation.model_dump(), default=str) if cand.evaluation else None,
            metadata_json=json.dumps(cand.metadata, default=str),
            created_at=cand.created_at,
            updated_at=cand.updated_at,
        )

    async def get_candidate(self, candidate_id: str) -> Optional[SubagentCandidate]:
        stmt = select(SubagentCandidateORM).where(SubagentCandidateORM.id == candidate_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._candidate_to_domain(orm) if orm else None

    async def save_candidate(self, candidate: SubagentCandidate) -> None:
        existing = await self._session.get(SubagentCandidateORM, candidate.candidate_id)
        if existing:
            existing.status = candidate.status.value
            existing.risk_level = candidate.risk_level.value
            existing.is_high_risk = candidate.is_high_risk
            existing.proposed_spec_json = json.dumps(candidate.proposed_spec, default=str)
            existing.reasoning_summary = candidate.reasoning_summary
            existing.supporting_experiences_json = json.dumps(candidate.supporting_experiences)
            existing.security_audit_json = (
                json.dumps(candidate.security_audit.model_dump(), default=str) if candidate.security_audit else None
            )
            existing.evaluation_json = (
                json.dumps(candidate.evaluation.model_dump(), default=str) if candidate.evaluation else None
            )
            existing.metadata_json = json.dumps(candidate.metadata, default=str)
            existing.updated_at = candidate.updated_at
        else:
            orm = self._candidate_to_orm(candidate)
            self._session.add(orm)
        await self._session.flush()

    async def list_candidates(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentCandidate]:
        stmt = select(SubagentCandidateORM).order_by(desc(SubagentCandidateORM.created_at)).limit(limit)
        if role:
            stmt = stmt.where(SubagentCandidateORM.role == role)
        if status:
            stmt = stmt.where(SubagentCandidateORM.status == status)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [self._candidate_to_domain(o) for o in orms]

    # -------------------------------------------------------------------------
    # Spec Version operations
    # -------------------------------------------------------------------------

    def _spec_to_domain(self, orm: SubagentSpecVersionORM) -> SubagentSpecVersion:
        routing_raw = _parse_json(orm.model_routing_policy_json, {})
        routing_policy = ModelRoutingPolicy(**routing_raw)

        mem_raw = _parse_json(orm.memory_access_json, {})
        memory_access = MemoryAccessPolicy(**mem_raw)

        budget_raw = _parse_json(orm.max_budget_json, {})
        max_budget = AgentBudgetLimits(**budget_raw)

        contract_raw = _parse_json(orm.output_contract_json, {})
        output_contract = SubagentOutputContract(**contract_raw)

        return SubagentSpecVersion(
            id=orm.id,
            role=orm.role,
            version=orm.version,
            parent_version=orm.parent_version,
            objective=orm.objective,
            system_supplement=orm.system_supplement,
            allowed_tools=_parse_json(orm.allowed_tools_json, []),
            allowed_skills=_parse_json(orm.allowed_skills_json, []),
            model_routing_policy=routing_policy,
            memory_access=memory_access,
            max_budget=max_budget,
            max_depth=orm.max_depth,
            output_contract=output_contract,
            status=SubagentSpecStatus(orm.status),
            risk_level=SubagentRiskLevel(orm.risk_level),
            spec_hash=orm.spec_hash,
            promoted_from_candidate_id=orm.promoted_from_candidate_id,
            security_audit_id=orm.security_audit_id,
            evaluation_id=orm.evaluation_id,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            activated_at=orm.activated_at,
            deprecated_at=orm.deprecated_at,
        )

    def _spec_to_orm(self, spec: SubagentSpecVersion) -> SubagentSpecVersionORM:
        return SubagentSpecVersionORM(
            id=spec.id,
            role=spec.role,
            version=spec.version,
            parent_version=spec.parent_version,
            objective=spec.objective,
            system_supplement=spec.system_supplement,
            allowed_tools_json=json.dumps(spec.allowed_tools),
            allowed_skills_json=json.dumps(spec.allowed_skills),
            model_routing_policy_json=json.dumps(spec.model_routing_policy.model_dump(), default=str),
            memory_access_json=json.dumps(spec.memory_access.model_dump(), default=str),
            max_budget_json=json.dumps(spec.max_budget.model_dump(), default=str),
            max_depth=spec.max_depth,
            output_contract_json=json.dumps(spec.output_contract.model_dump(), default=str),
            status=spec.status.value,
            risk_level=spec.risk_level.value,
            spec_hash=spec.spec_hash or spec.compute_spec_hash(),
            promoted_from_candidate_id=spec.promoted_from_candidate_id,
            security_audit_id=spec.security_audit_id,
            evaluation_id=spec.evaluation_id,
            metadata_json=json.dumps(spec.metadata, default=str),
            created_at=spec.created_at,
            activated_at=spec.activated_at,
            deprecated_at=spec.deprecated_at,
        )

    async def get_spec(self, spec_id: str) -> Optional[SubagentSpecVersion]:
        stmt = select(SubagentSpecVersionORM).where(SubagentSpecVersionORM.id == spec_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._spec_to_domain(orm) if orm else None

    async def get_spec_by_semver(self, role: str, version: str) -> Optional[SubagentSpecVersion]:
        stmt = (
            select(SubagentSpecVersionORM)
            .where(SubagentSpecVersionORM.role == role)
            .where(SubagentSpecVersionORM.version == version)
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._spec_to_domain(orm) if orm else None

    async def get_active_spec(self, role: str) -> Optional[SubagentSpecVersion]:
        stmt = (
            select(SubagentSpecVersionORM)
            .where(SubagentSpecVersionORM.role == role)
            .where(SubagentSpecVersionORM.status == SubagentSpecStatus.ACTIVE.value)
            .order_by(desc(SubagentSpecVersionORM.created_at))
            .limit(1)
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._spec_to_domain(orm) if orm else None

    async def save_spec(self, spec: SubagentSpecVersion) -> None:
        existing = await self._session.get(SubagentSpecVersionORM, spec.id)
        if existing:
            existing.status = spec.status.value
            existing.risk_level = spec.risk_level.value
            existing.objective = spec.objective
            existing.system_supplement = spec.system_supplement
            existing.allowed_tools_json = json.dumps(spec.allowed_tools)
            existing.allowed_skills_json = json.dumps(spec.allowed_skills)
            existing.model_routing_policy_json = json.dumps(spec.model_routing_policy.model_dump(), default=str)
            existing.memory_access_json = json.dumps(spec.memory_access.model_dump(), default=str)
            existing.max_budget_json = json.dumps(spec.max_budget.model_dump(), default=str)
            existing.max_depth = spec.max_depth
            existing.output_contract_json = json.dumps(spec.output_contract.model_dump(), default=str)
            existing.spec_hash = spec.spec_hash or spec.compute_spec_hash()
            existing.activated_at = spec.activated_at
            existing.deprecated_at = spec.deprecated_at
            existing.metadata_json = json.dumps(spec.metadata, default=str)
        else:
            orm = self._spec_to_orm(spec)
            self._session.add(orm)
        await self._session.flush()

    async def list_specs(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentSpecVersion]:
        stmt = select(SubagentSpecVersionORM).order_by(desc(SubagentSpecVersionORM.created_at)).limit(limit)
        if role:
            stmt = stmt.where(SubagentSpecVersionORM.role == role)
        if status:
            stmt = stmt.where(SubagentSpecVersionORM.status == status)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [self._spec_to_domain(o) for o in orms]

    # -------------------------------------------------------------------------
    # Promotion operations
    # -------------------------------------------------------------------------

    def _promotion_to_domain(self, orm: SubagentPromotionDecisionORM) -> SubagentPromotionDecision:
        return SubagentPromotionDecision(
            id=orm.id,
            candidate_id=orm.candidate_id,
            role=orm.role,
            source_version=orm.source_version,
            target_version=orm.target_version,
            status=SubagentPromotionStatus(orm.status),
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

    def _promotion_to_orm(self, prom: SubagentPromotionDecision) -> SubagentPromotionDecisionORM:
        return SubagentPromotionDecisionORM(
            id=prom.id,
            candidate_id=prom.candidate_id,
            role=prom.role,
            source_version=prom.source_version,
            target_version=prom.target_version,
            status=prom.status.value,
            security_audit_passed=prom.security_audit_passed,
            evaluation_passed=prom.evaluation_passed,
            requires_human_approval=prom.requires_human_approval,
            approved_by=prom.approved_by,
            approved_at=prom.approved_at,
            rejection_reason=prom.rejection_reason,
            decision_rationale=prom.decision_rationale,
            created_at=prom.created_at,
            updated_at=prom.updated_at,
        )

    async def get_promotion(self, decision_id: str) -> Optional[SubagentPromotionDecision]:
        stmt = select(SubagentPromotionDecisionORM).where(SubagentPromotionDecisionORM.id == decision_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._promotion_to_domain(orm) if orm else None

    async def save_promotion(self, decision: SubagentPromotionDecision) -> None:
        existing = await self._session.get(SubagentPromotionDecisionORM, decision.id)
        if existing:
            existing.status = decision.status.value
            existing.approved_by = decision.approved_by
            existing.approved_at = decision.approved_at
            existing.rejection_reason = decision.rejection_reason
            existing.decision_rationale = decision.decision_rationale
            existing.updated_at = decision.updated_at
        else:
            orm = self._promotion_to_orm(decision)
            self._session.add(orm)
        await self._session.flush()

    async def list_promotions(
        self,
        role: Optional[str] = None,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentPromotionDecision]:
        stmt = select(SubagentPromotionDecisionORM).order_by(desc(SubagentPromotionDecisionORM.created_at)).limit(limit)
        if role:
            stmt = stmt.where(SubagentPromotionDecisionORM.role == role)
        if candidate_id:
            stmt = stmt.where(SubagentPromotionDecisionORM.candidate_id == candidate_id)
        if status:
            stmt = stmt.where(SubagentPromotionDecisionORM.status == status)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [self._promotion_to_domain(o) for o in orms]

