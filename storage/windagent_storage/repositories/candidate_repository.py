"""Candidate & Learned Rule Repository (Async SQL) for Phase 9 (ban_ke_hoach_v1 §14, §23, §24)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearnedRule,
    LearnedRuleState,
    LearningCandidate,
)
from windagent_storage.orm.candidate_models import LearnedRuleORM, LearningCandidateORM

logger = logging.getLogger("windagent.storage.repositories.candidate")


class CandidateRepository:
    """Durable async repository for storing and querying LearningCandidates and LearnedRules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _candidate_to_domain(self, orm: LearningCandidateORM) -> LearningCandidate:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return LearningCandidate(
            candidate_id=orm.id,
            kind=CandidateKind(orm.kind),
            condition=orm.condition,
            proposed_change=_parse_json(orm.proposed_change_json, {}),
            reasoning_summary=orm.reasoning_summary,
            supporting_experiences=_parse_json(orm.supporting_experiences_json, []),
            counter_evidence=_parse_json(orm.counter_evidence_json, []),
            sample_size=orm.sample_size,
            confidence=float(orm.confidence),
            scope=CandidateScope(orm.scope),
            risk_level=CandidateRiskLevel(orm.risk_level),
            status=CandidateStatus(orm.status),
            project_id=orm.project_id,
            domain=orm.domain,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _rule_to_domain(self, orm: LearnedRuleORM) -> LearnedRule:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return LearnedRule(
            rule_id=orm.id,
            condition=orm.condition,
            recommendation=orm.recommendation,
            domain=orm.domain,
            scope=CandidateScope(orm.scope),
            evidence_refs=_parse_json(orm.evidence_refs_json, []),
            metrics=_parse_json(orm.metrics_json, {}),
            confidence=float(orm.confidence),
            sample_size=orm.sample_size,
            created_at=orm.created_at,
            last_validated_at=orm.last_validated_at,
            harness_version=orm.harness_version,
            version=orm.version,
            state=LearnedRuleState(orm.state),
        )

    async def save(
        self,
        candidate: Union[LearningCandidate, Dict[str, Any]],
    ) -> LearningCandidate:
        """Persists or updates a LearningCandidate record."""
        if not isinstance(candidate, LearningCandidate):
            candidate = LearningCandidate.model_validate(candidate)

        now = datetime.now(timezone.utc)
        proposed_change_json = json.dumps(candidate.proposed_change, default=str)
        supporting_json = json.dumps(candidate.supporting_experiences, default=str)
        counter_json = json.dumps(candidate.counter_evidence, default=str)
        metadata_json = json.dumps(candidate.metadata, default=str)

        existing = await self._session.get(LearningCandidateORM, candidate.candidate_id)
        if not existing:
            orm = LearningCandidateORM(
                id=candidate.candidate_id,
                kind=candidate.kind.value,
                condition=candidate.condition,
                proposed_change_json=proposed_change_json,
                reasoning_summary=candidate.reasoning_summary,
                supporting_experiences_json=supporting_json,
                counter_evidence_json=counter_json,
                sample_size=candidate.sample_size,
                confidence=candidate.confidence,
                scope=candidate.scope.value,
                risk_level=candidate.risk_level.value,
                status=candidate.status.value,
                project_id=candidate.project_id,
                domain=candidate.domain,
                metadata_json=metadata_json,
                created_at=candidate.created_at or now,
                updated_at=candidate.updated_at or now,
            )
            self._session.add(orm)
            await self._session.flush()
            return candidate

        existing.kind = candidate.kind.value
        existing.condition = candidate.condition
        existing.proposed_change_json = proposed_change_json
        existing.reasoning_summary = candidate.reasoning_summary
        existing.supporting_experiences_json = supporting_json
        existing.counter_evidence_json = counter_json
        existing.sample_size = candidate.sample_size
        existing.confidence = candidate.confidence
        existing.scope = candidate.scope.value
        existing.risk_level = candidate.risk_level.value
        existing.status = candidate.status.value
        existing.project_id = candidate.project_id
        existing.domain = candidate.domain
        existing.metadata_json = metadata_json
        existing.updated_at = now
        await self._session.flush()
        return candidate

    async def save_batch(
        self,
        candidates: Sequence[Union[LearningCandidate, Dict[str, Any]]],
    ) -> List[LearningCandidate]:
        """Persists a batch of LearningCandidate records."""
        saved = []
        for cand in candidates:
            persisted = await self.save(cand)
            saved.append(persisted)
        return saved

    async def get_by_id(self, candidate_id: str) -> Optional[LearningCandidate]:
        """Retrieves a single candidate by ID."""
        orm = await self._session.get(LearningCandidateORM, candidate_id)
        if not orm:
            return None
        return self._candidate_to_domain(orm)

    async def list_candidates(
        self,
        status: Optional[CandidateStatus] = None,
        kind: Optional[CandidateKind] = None,
        scope: Optional[CandidateScope] = None,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LearningCandidate]:
        """Lists candidates matching filter criteria."""
        stmt = select(LearningCandidateORM)
        if status:
            stmt = stmt.where(LearningCandidateORM.status == status.value)
        if kind:
            stmt = stmt.where(LearningCandidateORM.kind == kind.value)
        if scope:
            stmt = stmt.where(LearningCandidateORM.scope == scope.value)
        if project_id:
            stmt = stmt.where(LearningCandidateORM.project_id == project_id)
        if domain:
            stmt = stmt.where(LearningCandidateORM.domain == domain)
        if min_confidence > 0.0:
            stmt = stmt.where(LearningCandidateORM.confidence >= min_confidence)

        stmt = stmt.order_by(LearningCandidateORM.confidence.desc(), LearningCandidateORM.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        res = await self._session.execute(stmt)
        return [self._candidate_to_domain(r) for r in res.scalars().all()]

    async def update_status(
        self,
        candidate_id: str,
        new_status: CandidateStatus,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> Optional[LearningCandidate]:
        """Updates candidate status and metadata."""
        orm = await self._session.get(LearningCandidateORM, candidate_id)
        if not orm:
            return None

        orm.status = new_status.value
        if metadata_update:
            try:
                meta = json.loads(orm.metadata_json or "{}")
            except Exception:
                meta = {}
            meta.update(metadata_update)
            orm.metadata_json = json.dumps(meta, default=str)

        orm.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._candidate_to_domain(orm)

    async def delete_candidate(self, candidate_id: str) -> bool:
        """Deletes a candidate record."""
        orm = await self._session.get(LearningCandidateORM, candidate_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    async def save_rule(
        self,
        rule: Union[LearnedRule, Dict[str, Any]],
    ) -> LearnedRule:
        """Persists or updates a LearnedRule record."""
        if not isinstance(rule, LearnedRule):
            rule = LearnedRule.model_validate(rule)

        now = datetime.now(timezone.utc)
        evidence_json = json.dumps(rule.evidence_refs, default=str)
        metrics_json = json.dumps(rule.metrics, default=str)

        existing = await self._session.get(LearnedRuleORM, rule.rule_id)
        if not existing:
            orm = LearnedRuleORM(
                id=rule.rule_id,
                condition=rule.condition,
                recommendation=rule.recommendation,
                domain=rule.domain,
                scope=rule.scope.value,
                evidence_refs_json=evidence_json,
                metrics_json=metrics_json,
                confidence=rule.confidence,
                sample_size=rule.sample_size,
                created_at=rule.created_at or now,
                last_validated_at=rule.last_validated_at,
                harness_version=rule.harness_version,
                version=rule.version,
                state=rule.state.value,
            )
            self._session.add(orm)
            await self._session.flush()
            return rule

        existing.condition = rule.condition
        existing.recommendation = rule.recommendation
        existing.domain = rule.domain
        existing.scope = rule.scope.value
        existing.evidence_refs_json = evidence_json
        existing.metrics_json = metrics_json
        existing.confidence = rule.confidence
        existing.sample_size = rule.sample_size
        existing.last_validated_at = rule.last_validated_at
        existing.harness_version = rule.harness_version
        existing.version = rule.version
        existing.state = rule.state.value
        await self._session.flush()
        return rule

    async def get_rule_by_id(self, rule_id: str) -> Optional[LearnedRule]:
        """Retrieves a single LearnedRule by ID."""
        orm = await self._session.get(LearnedRuleORM, rule_id)
        if not orm:
            return None
        return self._rule_to_domain(orm)

    async def list_rules(
        self,
        domain: Optional[str] = None,
        state: Optional[LearnedRuleState] = None,
        limit: int = 100,
    ) -> List[LearnedRule]:
        """Lists learned rules with optional domain and state filters."""
        stmt = select(LearnedRuleORM)
        if domain:
            stmt = stmt.where(LearnedRuleORM.domain == domain)
        if state:
            stmt = stmt.where(LearnedRuleORM.state == state.value)
        stmt = stmt.order_by(LearnedRuleORM.confidence.desc(), LearnedRuleORM.created_at.desc()).limit(limit)

        res = await self._session.execute(stmt)
        return [self._rule_to_domain(r) for r in res.scalars().all()]

    async def delete_rule(self, rule_id: str) -> bool:
        """Deletes a LearnedRule record."""
        orm = await self._session.get(LearnedRuleORM, rule_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

