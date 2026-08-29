"""Candidate Service Coordinator (Phase 9 — ban_ke_hoach_v1 §14 & §26).

Coordinates candidate generation, clustering/mining from empirical experiences,
eligibility evaluation, and candidate lifecycle state transitions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.experience import Experience

from windagent_intelligence.candidate.candidate_generator import (
    CandidateGenerator,
    generate_candidate_id,
)
from windagent_intelligence.candidate.eligibility_gate import EligibilityGate


class CandidateService:
    """Service orchestrating candidate learning lifecycle operations."""

    def __init__(self, repository: Optional[Any] = None) -> None:
        self._repository = repository

    async def propose_candidate(
        self,
        kind: CandidateKind,
        condition: str,
        proposed_change: Dict[str, Any],
        reasoning_summary: str,
        supporting_experiences: Optional[List[str]] = None,
        counter_evidence: Optional[List[str]] = None,
        sample_size: int = 1,
        confidence: float = 0.5,
        scope: CandidateScope = CandidateScope.PROJECT,
        risk_level: CandidateRiskLevel = CandidateRiskLevel.MEDIUM,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LearningCandidate:
        """Proposes a new LearningCandidate and optionally saves to repository."""
        cand_id = generate_candidate_id()
        candidate = LearningCandidate(
            candidate_id=cand_id,
            kind=kind,
            condition=condition,
            proposed_change=proposed_change,
            reasoning_summary=reasoning_summary,
            supporting_experiences=supporting_experiences or [],
            counter_evidence=counter_evidence or [],
            sample_size=sample_size,
            confidence=confidence,
            scope=scope,
            risk_level=risk_level,
            status=CandidateStatus.PROPOSED,
            project_id=project_id,
            domain=domain,
            metadata=metadata or {},
        )
        candidate.assert_candidate_invariants()

        if self._repository:
            await self._repository.save(candidate)

        return candidate

    async def generate_from_experience(
        self,
        experience: Experience,
        kind: Optional[CandidateKind] = None,
        scope: CandidateScope = CandidateScope.PROJECT,
    ) -> LearningCandidate:
        """Generates a PROPOSED candidate from a single diagnosed experience."""
        candidate = CandidateGenerator.generate_from_single_experience(
            experience=experience,
            kind=kind,
            scope=scope,
        )
        candidate.assert_candidate_invariants()

        if self._repository:
            await self._repository.save(candidate)

        return candidate

    async def mine_from_experiences(
        self,
        experiences: Sequence[Experience],
        min_cluster_size: int = 2,
        scope: CandidateScope = CandidateScope.PROJECT,
    ) -> List[LearningCandidate]:
        """Mines clustered learning candidates from a collection of experiences."""
        candidates = CandidateGenerator.mine_candidates_from_experiences(
            experiences=experiences,
            min_cluster_size=min_cluster_size,
            scope=scope,
        )

        for cand in candidates:
            cand.assert_candidate_invariants()

        if self._repository and candidates:
            await self._repository.save_batch(candidates)

        return candidates

    def evaluate_eligibility(
        self,
        candidate: LearningCandidate,
        min_sample_size: Optional[int] = None,
        min_confidence: Optional[float] = None,
        max_counter_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Checks if candidate qualifies for ELIGIBLE status without mutating it."""
        return EligibilityGate.evaluate(
            candidate=candidate,
            min_sample_size=min_sample_size,
            min_confidence=min_confidence,
            max_counter_ratio=max_counter_ratio,
        )

    async def mark_eligible(
        self,
        candidate: LearningCandidate,
        min_sample_size: Optional[int] = None,
        min_confidence: Optional[float] = None,
        max_counter_ratio: Optional[float] = None,
    ) -> LearningCandidate:
        """Transitions candidate to ELIGIBLE state after passing eligibility checks."""
        eligible_candidate = EligibilityGate.apply(
            candidate=candidate,
            min_sample_size=min_sample_size,
            min_confidence=min_confidence,
            max_counter_ratio=max_counter_ratio,
        )

        if self._repository:
            await self._repository.save(eligible_candidate)

        return eligible_candidate

    async def reject_candidate(
        self,
        candidate: LearningCandidate,
        reason: str,
    ) -> LearningCandidate:
        """Transitions candidate to REJECTED state."""
        rejected_candidate = candidate.reject(reason=reason)

        if self._repository:
            await self._repository.save(rejected_candidate)

        return rejected_candidate

    async def expire_candidate(
        self,
        candidate: LearningCandidate,
    ) -> LearningCandidate:
        """Transitions candidate to EXPIRED state."""
        expired_candidate = candidate.expire()

        if self._repository:
            await self._repository.save(expired_candidate)

        return expired_candidate

    async def get_candidate(self, candidate_id: str) -> Optional[LearningCandidate]:
        """Retrieves candidate by ID from repository."""
        if not self._repository:
            return None
        return await self._repository.get_by_id(candidate_id)

    async def list_candidates(
        self,
        status: Optional[CandidateStatus] = None,
        kind: Optional[CandidateKind] = None,
        scope: Optional[CandidateScope] = None,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LearningCandidate]:
        """Lists filtered candidates from repository."""
        if not self._repository:
            return []
        return await self._repository.list_candidates(
            status=status,
            kind=kind,
            scope=scope,
            project_id=project_id,
            domain=domain,
            limit=limit,
            offset=offset,
        )
