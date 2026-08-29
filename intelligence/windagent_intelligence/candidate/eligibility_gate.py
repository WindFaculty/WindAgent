"""Eligibility Gate for Learning Candidates (Phase 9 — ban_ke_hoach_v1 §14 & §35).

Enforces statistical sample size, confidence thresholds, counter-evidence limits,
and risk controls before admitting a LearningCandidate into the ELIGIBLE state.

Invariants:
- Single failure / observation candidates (sample_size=1) CANNOT be eligible.
- Global / high-risk mutations require stricter sample size and confidence.
- Counter-evidence ratio must not exceed tolerance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)


class EligibilityGate:
    """Evaluates and enforces qualification criteria for LearningCandidates."""

    DEFAULT_MIN_CONFIDENCE = 0.65
    DEFAULT_MAX_COUNTER_RATIO = 0.35

    SAMPLE_SIZE_THRESHOLDS = {
        CandidateScope.LOCAL: 2,
        CandidateScope.PROJECT: 3,
        CandidateScope.GLOBAL: 5,
    }

    @classmethod
    def evaluate(
        cls,
        candidate: LearningCandidate,
        min_sample_size: Optional[int] = None,
        min_confidence: Optional[float] = None,
        max_counter_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Evaluates whether a candidate satisfies eligibility criteria without mutating it."""
        reasons: List[str] = []
        is_eligible = True

        # 1. State check
        if candidate.status not in (CandidateStatus.PROPOSED, CandidateStatus.ELIGIBLE):
            return {
                "eligible": False,
                "reasons": [f"Candidate status '{candidate.status.value}' cannot transition to ELIGIBLE."],
                "details": {},
            }

        # 2. Scope-based sample size requirement
        required_sample_size = (
            min_sample_size
            if min_sample_size is not None
            else cls.SAMPLE_SIZE_THRESHOLDS.get(candidate.scope, 3)
        )

        # High/Critical risk increases required sample size
        if candidate.risk_level in (CandidateRiskLevel.HIGH, CandidateRiskLevel.CRITICAL):
            required_sample_size = max(required_sample_size, 5)

        if candidate.sample_size < required_sample_size:
            is_eligible = False
            reasons.append(
                f"Sample size ({candidate.sample_size}) is below threshold ({required_sample_size}) "
                f"for scope '{candidate.scope.value}' and risk '{candidate.risk_level.value}'."
            )

        # 3. Confidence requirement
        required_confidence = min_confidence if min_confidence is not None else cls.DEFAULT_MIN_CONFIDENCE
        if candidate.risk_level in (CandidateRiskLevel.HIGH, CandidateRiskLevel.CRITICAL):
            required_confidence = max(required_confidence, 0.80)

        if candidate.confidence < required_confidence:
            is_eligible = False
            reasons.append(
                f"Confidence ({candidate.confidence:.2f}) is below required threshold ({required_confidence:.2f})."
            )

        # 4. Counter-evidence ratio check
        allowed_counter_ratio = (
            max_counter_ratio if max_counter_ratio is not None else cls.DEFAULT_MAX_COUNTER_RATIO
        )
        total_evidence = len(candidate.supporting_experiences) + len(candidate.counter_evidence)
        counter_ratio = (len(candidate.counter_evidence) / total_evidence) if total_evidence > 0 else 0.0

        if counter_ratio > allowed_counter_ratio:
            is_eligible = False
            reasons.append(
                f"Counter-evidence ratio ({counter_ratio:.2f}) exceeds allowed tolerance ({allowed_counter_ratio:.2f})."
            )

        # 5. Safety check
        lower_reasoning = candidate.reasoning_summary.lower()
        if "bypass" in lower_reasoning or "ignore safety" in lower_reasoning or "disable policy" in lower_reasoning:
            is_eligible = False
            reasons.append("Zero-tolerance safety invariant: candidate attempts to bypass or disable security/safety policies.")

        # Determine suggested risk level
        suggested_risk = candidate.risk_level
        if candidate.scope == CandidateScope.GLOBAL or candidate.kind in (
            CandidateKind.SKILL,
            CandidateKind.ROUTING_POLICY,
        ):
            suggested_risk = CandidateRiskLevel.HIGH

        return {
            "eligible": is_eligible,
            "reasons": reasons,
            "details": {
                "candidate_id": candidate.candidate_id,
                "current_status": candidate.status.value,
                "sample_size": candidate.sample_size,
                "required_sample_size": required_sample_size,
                "confidence": candidate.confidence,
                "required_confidence": required_confidence,
                "counter_ratio": round(counter_ratio, 4),
                "allowed_counter_ratio": allowed_counter_ratio,
                "suggested_risk_level": suggested_risk.value,
            },
        }

    @classmethod
    def apply(
        cls,
        candidate: LearningCandidate,
        min_sample_size: Optional[int] = None,
        min_confidence: Optional[float] = None,
        max_counter_ratio: Optional[float] = None,
    ) -> LearningCandidate:
        """Evaluates eligibility and returns an immutable candidate transitioned to ELIGIBLE or raises ValueError."""
        eval_result = cls.evaluate(
            candidate,
            min_sample_size=min_sample_size,
            min_confidence=min_confidence,
            max_counter_ratio=max_counter_ratio,
        )

        if not eval_result["eligible"]:
            error_msg = "; ".join(eval_result["reasons"])
            raise ValueError(f"Eligibility gate rejected candidate {candidate.candidate_id}: {error_msg}")

        req_sample = eval_result["details"]["required_sample_size"]
        req_conf = eval_result["details"]["required_confidence"]
        req_counter = eval_result["details"]["allowed_counter_ratio"]

        return candidate.mark_eligible(
            min_sample_size=req_sample,
            min_confidence=req_conf,
            max_counter_ratio=req_counter,
        )

