"""
Verdict policy (plan 05 Phase 20 §25.4, gate VP20_GENERATION_REVIEW_VERIFIED).

Decides APPROVE / REJECT / HUMAN_REVIEW_REQUIRED / REVIEW_ERROR from the
collected dimension results + blocking defects.

Rules (plan §25.4):

- a blocking defect ALWAYS wins over any aggregate preference — a candidate
  with a high average score but a blocking defect is REJECT, never selected;
- REVIEW_ERROR (VLM timeout / invalid output / schema violation) is never a
  PASS — it produces REVIEW_ERROR;
- LOW confidence on any dimension routes to HUMAN_REVIEW_REQUIRED;
- thresholds come from the versioned dimension catalog; a policy change is a
  NEW policy version and never rewrites old results (plan §26);
- never auto-approve a candidate with a blocking defect or an error.
"""

from __future__ import annotations

from typing import Tuple

from windagent_intelligence.video.reviewers.dimensions import (
    REVIEW_POLICY_VERSION,
    config_for,
)
from windagent_intelligence.video.reviewers.models import (
    BlockingDefect,
    BlockingReasonCode,
    CandidateReview,
    CandidateVerdict,
    DimensionResult,
)

VERDICT_POLICY_VERSION = REVIEW_POLICY_VERSION


class VerdictPolicy:
    """Deterministic verdict policy (plan §25.4)."""

    def __init__(self, policy_version: str = VERDICT_POLICY_VERSION) -> None:
        self.policy_version = policy_version

    def decide(
        self,
        *,
        candidate_id: str,
        request_hash: str,
        shot_id: str,
        dimensions: Tuple[DimensionResult, ...],
        blocking_defects: Tuple[BlockingDefect, ...],
        reviewed_at: float = 0.0,
    ) -> CandidateReview:
        """Produce the candidate review with the policy verdict.

        Order of checks (fail closed first):

        1. any REVIEW_ERROR defect            -> REVIEW_ERROR;
        2. any blocking defect                -> REJECT (blocking wins);
        3. any dimension below its threshold  -> REJECT;
        4. any dimension confidence < floor   -> HUMAN_REVIEW_REQUIRED;
        5. otherwise                          -> APPROVE.
        """
        error_defects = [
            d for d in blocking_defects if d.code == BlockingReasonCode.REVIEW_ERROR
        ]
        if error_defects:
            return self._build(
                candidate_id, request_hash, shot_id, dimensions, blocking_defects,
                CandidateVerdict.REVIEW_ERROR,
                f"review error: {error_defects[0].message}",
                reviewed_at,
            )

        blocking = [d for d in blocking_defects if d.code != BlockingReasonCode.REVIEW_ERROR]
        if blocking:
            return self._build(
                candidate_id, request_hash, shot_id, dimensions, blocking_defects,
                CandidateVerdict.REJECT,
                f"blocking defect: {blocking[0].message}",
                reviewed_at,
            )

        below_threshold = [
            d for d in dimensions
            if d.score < config_for(d.dimension).pass_threshold
        ]
        if below_threshold:
            return self._build(
                candidate_id, request_hash, shot_id, dimensions, blocking_defects,
                CandidateVerdict.REJECT,
                f"dimension below threshold: {below_threshold[0].dimension.value} "
                f"(score {below_threshold[0].score:.2f})",
                reviewed_at,
            )

        low_confidence = [
            d for d in dimensions
            if d.confidence < config_for(d.dimension).confidence_floor
        ]
        if low_confidence:
            return self._build(
                candidate_id, request_hash, shot_id, dimensions, blocking_defects,
                CandidateVerdict.HUMAN_REVIEW_REQUIRED,
                f"low confidence: {low_confidence[0].dimension.value} "
                f"(confidence {low_confidence[0].confidence:.2f})",
                reviewed_at,
            )

        return self._build(
            candidate_id, request_hash, shot_id, dimensions, blocking_defects,
            CandidateVerdict.APPROVE,
            "all dimensions pass with sufficient confidence; no blocking defects",
            reviewed_at,
        )

    def _build(
        self,
        candidate_id: str,
        request_hash: str,
        shot_id: str,
        dimensions: Tuple[DimensionResult, ...],
        blocking_defects: Tuple[BlockingDefect, ...],
        verdict: CandidateVerdict,
        reason: str,
        reviewed_at: float,
    ) -> CandidateReview:
        # The review identity binds the candidate AND the policy version:
        # a policy/threshold change produces a NEW review revision, it never
        # rewrites the previous result (plan §26).
        return CandidateReview(
            review_id=f"rv_{candidate_id}:{self.policy_version}",
            candidate_id=candidate_id,
            request_hash=request_hash,
            shot_id=shot_id,
            dimensions=dimensions,
            blocking_defects=blocking_defects,
            verdict=verdict,
            policy_version=self.policy_version,
            reason=reason,
            reviewed_at=reviewed_at,
        )


__all__ = ["VERDICT_POLICY_VERSION", "VerdictPolicy"]
