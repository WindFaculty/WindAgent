"""Organizational Learning Repository (Async SQL) for Phase 14 (ban_ke_hoach_v1 §20, §23, §24, §25)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.organizational_learning import (
    ConflictResolutionRecord,
    KnowledgeVisibilityScope,
    LearnedRule,
    LearnedRuleState,
    MultiAgentAttributionRecord,
)
from windagent_storage.orm.candidate_models import LearnedRuleORM
from windagent_storage.orm.organizational_learning_models import (
    ConflictResolutionORM,
    MultiAgentAttributionORM,
)

logger = logging.getLogger("windagent.storage.repositories.organizational_learning")


def _parse_json(val: Optional[str], default: Any) -> Any:
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


def _parse_condition(cond: Any) -> Dict[str, Any]:
    if isinstance(cond, dict):
        return cond
    if isinstance(cond, str):
        try:
            parsed = json.loads(cond)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"raw": cond}
    return {}


class OrganizationalLearningRepository:
    """Async SQL repository implementing OrganizationalLearningRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -------------------------------------------------------------------------
    # Learned Rule Operations
    # -------------------------------------------------------------------------

    def _rule_to_domain(self, orm: LearnedRuleORM) -> LearnedRule:
        return LearnedRule(
            rule_id=orm.id,
            domain=orm.domain,
            condition=_parse_condition(orm.condition),
            recommendation=orm.recommendation,
            scope=KnowledgeVisibilityScope(orm.scope),
            target_role=getattr(orm, "target_role", None),
            project_id=getattr(orm, "project_id", None),
            evidence_refs=_parse_json(orm.evidence_refs_json, []),
            metrics=_parse_json(orm.metrics_json, {}),
            confidence=float(orm.confidence),
            sample_size=int(orm.sample_size),
            harness_version=orm.harness_version,
            version=int(orm.version),
            state=LearnedRuleState(orm.state),
            supersedes_id=getattr(orm, "supersedes_id", None),
            superseded_by=getattr(orm, "superseded_by", None),
            created_at=orm.created_at,
            last_validated_at=orm.last_validated_at,
            activated_at=getattr(orm, "activated_at", None),
            deprecated_at=getattr(orm, "deprecated_at", None),
            metadata=_parse_json(getattr(orm, "metadata_json", None), {}),
        )

    def _rule_to_orm(self, rule: LearnedRule) -> LearnedRuleORM:
        return LearnedRuleORM(
            id=rule.rule_id,
            domain=rule.domain,
            condition=json.dumps(rule.condition, default=str),
            recommendation=rule.recommendation,
            scope=rule.scope.value,
            target_role=rule.target_role,
            project_id=rule.project_id,
            evidence_refs_json=json.dumps(rule.evidence_refs, default=str),
            metrics_json=json.dumps(rule.metrics, default=str),
            confidence=rule.confidence,
            sample_size=rule.sample_size,
            harness_version=rule.harness_version,
            version=rule.version,
            state=rule.state.value,
            supersedes_id=rule.supersedes_id,
            superseded_by=rule.superseded_by,
            created_at=rule.created_at,
            last_validated_at=rule.last_validated_at,
            activated_at=rule.activated_at,
            deprecated_at=rule.deprecated_at,
            metadata_json=json.dumps(rule.metadata, default=str),
        )

    async def get_rule(self, rule_id: str) -> Optional[LearnedRule]:
        stmt = select(LearnedRuleORM).where(LearnedRuleORM.id == rule_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._rule_to_domain(orm) if orm else None

    async def save_rule(self, rule: LearnedRule) -> None:
        stmt = select(LearnedRuleORM).where(LearnedRuleORM.id == rule.rule_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.domain = rule.domain
            existing.condition = json.dumps(rule.condition, default=str)
            existing.recommendation = rule.recommendation
            existing.scope = rule.scope.value
            existing.target_role = rule.target_role
            existing.project_id = rule.project_id
            existing.evidence_refs_json = json.dumps(rule.evidence_refs, default=str)
            existing.metrics_json = json.dumps(rule.metrics, default=str)
            existing.confidence = rule.confidence
            existing.sample_size = rule.sample_size
            existing.harness_version = rule.harness_version
            existing.version = rule.version
            existing.state = rule.state.value
            existing.supersedes_id = rule.supersedes_id
            existing.superseded_by = rule.superseded_by
            existing.last_validated_at = rule.last_validated_at
            existing.activated_at = rule.activated_at
            existing.deprecated_at = rule.deprecated_at
            existing.metadata_json = json.dumps(rule.metadata, default=str)
        else:
            self._session.add(self._rule_to_orm(rule))

        await self._session.flush()

    async def list_rules(
        self,
        domain: Optional[str] = None,
        state: Optional[LearnedRuleState] = None,
        scope: Optional[KnowledgeVisibilityScope] = None,
        target_role: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[LearnedRule]:
        stmt = select(LearnedRuleORM)
        if domain:
            stmt = stmt.where(LearnedRuleORM.domain == domain)
        if state:
            stmt = stmt.where(LearnedRuleORM.state == state.value)
        if scope:
            stmt = stmt.where(LearnedRuleORM.scope == scope.value)
        if target_role:
            stmt = stmt.where(LearnedRuleORM.target_role == target_role)
        if project_id:
            stmt = stmt.where(LearnedRuleORM.project_id == project_id)

        stmt = stmt.order_by(desc(LearnedRuleORM.created_at)).limit(limit)
        res = await self._session.execute(stmt)
        return [self._rule_to_domain(orm) for orm in res.scalars().all()]

    async def query_active_rules(
        self,
        domain: str,
        target_role: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[LearnedRule]:
        stmt = select(LearnedRuleORM).where(
            LearnedRuleORM.domain == domain,
            LearnedRuleORM.state == LearnedRuleState.PROMOTED.value,
        )
        res = await self._session.execute(stmt)
        return [self._rule_to_domain(orm) for orm in res.scalars().all()]

    # -------------------------------------------------------------------------
    # Conflict Resolution Records
    # -------------------------------------------------------------------------

    def _resolution_to_domain(self, orm: ConflictResolutionORM) -> ConflictResolutionRecord:
        return ConflictResolutionRecord(
            resolution_id=orm.resolution_id,
            domain=orm.domain,
            context_query=_parse_json(orm.context_query_json, {}),
            winning_rule_id=orm.winning_rule_id,
            competing_rule_ids=_parse_json(orm.competing_rule_ids_json, []),
            resolution_rationale=orm.resolution_rationale,
            score_breakdown=_parse_json(orm.score_breakdown_json, {}),
            resolved_at=orm.resolved_at,
        )

    def _resolution_to_orm(self, record: ConflictResolutionRecord) -> ConflictResolutionORM:
        return ConflictResolutionORM(
            resolution_id=record.resolution_id,
            domain=record.domain,
            context_query_json=json.dumps(record.context_query, default=str),
            winning_rule_id=record.winning_rule_id,
            competing_rule_ids_json=json.dumps(record.competing_rule_ids, default=str),
            resolution_rationale=record.resolution_rationale,
            score_breakdown_json=json.dumps(record.score_breakdown, default=str),
            resolved_at=record.resolved_at,
        )

    async def get_conflict_resolution(self, resolution_id: str) -> Optional[ConflictResolutionRecord]:
        stmt = select(ConflictResolutionORM).where(ConflictResolutionORM.resolution_id == resolution_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._resolution_to_domain(orm) if orm else None

    async def save_conflict_resolution(self, record: ConflictResolutionRecord) -> None:
        self._session.add(self._resolution_to_orm(record))
        await self._session.flush()

    async def list_conflict_resolutions(
        self,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[ConflictResolutionRecord]:
        stmt = select(ConflictResolutionORM)
        if domain:
            stmt = stmt.where(ConflictResolutionORM.domain == domain)
        stmt = stmt.order_by(desc(ConflictResolutionORM.resolved_at)).limit(limit)
        res = await self._session.execute(stmt)
        return [self._resolution_to_domain(orm) for orm in res.scalars().all()]

    # -------------------------------------------------------------------------
    # Multi-Agent Attribution Records
    # -------------------------------------------------------------------------

    def _attribution_to_domain(self, orm: MultiAgentAttributionORM) -> MultiAgentAttributionRecord:
        return MultiAgentAttributionRecord(
            attribution_id=orm.attribution_id,
            episode_id=orm.episode_id,
            domain=orm.domain,
            metric_signals=_parse_json(orm.metric_signals_json, {}),
            role_attributions=_parse_json(orm.role_attributions_json, {}),
            created_at=orm.created_at,
        )

    def _attribution_to_orm(self, record: MultiAgentAttributionRecord) -> MultiAgentAttributionORM:
        return MultiAgentAttributionORM(
            attribution_id=record.attribution_id,
            episode_id=record.episode_id,
            domain=record.domain,
            metric_signals_json=json.dumps(record.metric_signals, default=str),
            role_attributions_json=json.dumps(record.role_attributions, default=str),
            created_at=record.created_at,
        )

    async def get_attribution(self, attribution_id: str) -> Optional[MultiAgentAttributionRecord]:
        stmt = select(MultiAgentAttributionORM).where(MultiAgentAttributionORM.attribution_id == attribution_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._attribution_to_domain(orm) if orm else None

    async def save_attribution(self, record: MultiAgentAttributionRecord) -> None:
        self._session.add(self._attribution_to_orm(record))
        await self._session.flush()

    async def list_attributions(
        self,
        episode_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[MultiAgentAttributionRecord]:
        stmt = select(MultiAgentAttributionORM)
        if episode_id:
            stmt = stmt.where(MultiAgentAttributionORM.episode_id == episode_id)
        if domain:
            stmt = stmt.where(MultiAgentAttributionORM.domain == domain)
        stmt = stmt.order_by(desc(MultiAgentAttributionORM.created_at)).limit(limit)
        res = await self._session.execute(stmt)
        return [self._attribution_to_domain(orm) for orm in res.scalars().all()]
