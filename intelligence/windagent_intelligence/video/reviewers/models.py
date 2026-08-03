"""
Candidate review domain models (plan 05 Phase 20 §23, §25.4-§25.5,
gate VP20_GENERATION_REVIEW_VERIFIED).

Review dimensions (plan §23):

    TECHNICAL_VALIDITY, PROMPT_COMPLIANCE, IDENTITY_CONSISTENCY,
    LOCATION_CONSISTENCY, PROP_CONSISTENCY, CONTINUITY, MOTION_QUALITY,
    CAMERA_COMPLIANCE, DIALOGUE_ALIGNMENT, VISUAL_ARTIFACTS, SAFETY

Each dimension result carries a score, a PASS/FAIL decision, confidence,
evidence, the metric/check version, the reviewer type (DETERMINISTIC / VLM /
CROSS_SHOT / HUMAN) and whether the dimension is a blocking rule.

Verdicts (plan §25.4):

    APPROVE, REJECT, HUMAN_REVIEW_REQUIRED, REVIEW_ERROR

Rules:

- a blocking defect ALWAYS wins over any aggregate preference — a candidate
  with high scores but a blocking defect is REJECT, never auto-selected;
- low confidence routes to human review; review/model errors never become a
  false PASS (REVIEW_ERROR);
- every dimension is traceable: metric version, model/prompt version,
  evidence, policy version — selection/rejection must trace back to policy,
  model and evidence (gate condition 4);
- rejected candidates keep their evidence; retry proposals record which
  defect to fix and which request field changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class ReviewDimension(str, Enum):
    """The 11 canonical review dimensions (plan 05 §23)."""

    TECHNICAL_VALIDITY = "TECHNICAL_VALIDITY"
    PROMPT_COMPLIANCE = "PROMPT_COMPLIANCE"
    IDENTITY_CONSISTENCY = "IDENTITY_CONSISTENCY"
    LOCATION_CONSISTENCY = "LOCATION_CONSISTENCY"
    PROP_CONSISTENCY = "PROP_CONSISTENCY"
    CONTINUITY = "CONTINUITY"
    MOTION_QUALITY = "MOTION_QUALITY"
    CAMERA_COMPLIANCE = "CAMERA_COMPLIANCE"
    DIALOGUE_ALIGNMENT = "DIALOGUE_ALIGNMENT"
    VISUAL_ARTIFACTS = "VISUAL_ARTIFACTS"
    SAFETY = "SAFETY"

    @classmethod
    def all_dimensions(cls) -> list[str]:
        return [d.value for d in cls]


class ReviewerType(str, Enum):
    """Reviewer that produced a dimension result (plan §24 hierarchy)."""

    DETERMINISTIC = "DETERMINISTIC"
    VLM = "VLM"
    CROSS_SHOT = "CROSS_SHOT"
    HUMAN = "HUMAN"


class CandidateVerdict(str, Enum):
    """Candidate-level verdict (plan 05 §25.4)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    REVIEW_ERROR = "REVIEW_ERROR"


class BlockingReasonCode(str, Enum):
    """Typed, machine-readable reasons for blocking defects (plan §25.3)."""

    MEDIA_DECODE_FAILURE = "MEDIA_DECODE_FAILURE"
    MISSING_VIDEO_STREAM = "MISSING_VIDEO_STREAM"
    INVALID_CONTENT_HASH = "INVALID_CONTENT_HASH"
    INVALID_DURATION = "INVALID_DURATION"
    MISSING_MEDIA_METADATA = "MISSING_MEDIA_METADATA"
    BLACK_ENDING = "BLACK_ENDING"
    TRUNCATED_ENDING = "TRUNCATED_ENDING"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    SAFETY_FINDING = "SAFETY_FINDING"
    PROMPT_COMPLIANCE = "PROMPT_COMPLIANCE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    PROP_MISMATCH = "PROP_MISMATCH"
    CAMERA_SIDE_VIOLATION = "CAMERA_SIDE_VIOLATION"
    SCREEN_DIRECTION_FLIP = "SCREEN_DIRECTION_FLIP"
    WARDROBE_MISMATCH = "WARDROBE_MISMATCH"
    LIGHTING_MISMATCH = "LIGHTING_MISMATCH"
    TAIL_HEAD_FRAME_RELATION = "TAIL_HEAD_FRAME_RELATION"
    CONTINUITY_VIOLATION = "CONTINUITY_VIOLATION"
    VISUAL_ARTIFACT = "VISUAL_ARTIFACT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    REVIEW_ERROR = "REVIEW_ERROR"


@dataclass(frozen=True)
class DimensionResult:
    """One dimension's review result (plan §23)."""

    dimension: ReviewDimension
    score: float  # 0..1 (or categorical normalized)
    passed: bool
    confidence: float  # 0..1
    metric_version: str
    reviewer_type: ReviewerType
    blocking_rule: bool = False
    evidence: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": self.score,
            "passed": self.passed,
            "confidence": self.confidence,
            "metric_version": self.metric_version,
            "reviewer_type": self.reviewer_type.value,
            "blocking_rule": self.blocking_rule,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class BlockingDefect:
    """A blocking defect with a typed reason code + evidence (plan §25.3)."""

    code: BlockingReasonCode
    dimension: ReviewDimension
    message: str
    reviewer_type: ReviewerType
    shot_id: Optional[str] = None
    evidence: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "dimension": self.dimension.value,
            "message": self.message,
            "reviewer_type": self.reviewer_type.value,
            "shot_id": self.shot_id,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class CandidateReview:
    """Full review of ONE generation candidate (plan §25)."""

    review_id: str
    candidate_id: str
    request_hash: str
    shot_id: str
    dimensions: Tuple[DimensionResult, ...]
    blocking_defects: Tuple[BlockingDefect, ...]
    verdict: CandidateVerdict
    policy_version: str
    model_versions: Dict[str, str] = field(default_factory=dict)
    reason: str = ""
    reviewed_at: float = 0.0

    @property
    def is_approvable(self) -> bool:
        return self.verdict == CandidateVerdict.APPROVE

    @property
    def dimension_scores(self) -> Dict[str, float]:
        return {d.dimension.value: d.score for d in self.dimensions}

    def average_score(self) -> float:
        if not self.dimensions:
            return 0.0
        return sum(d.score for d in self.dimensions) / len(self.dimensions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "candidate_id": self.candidate_id,
            "request_hash": self.request_hash,
            "shot_id": self.shot_id,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "blocking_defects": [b.to_dict() for b in self.blocking_defects],
            "verdict": self.verdict.value,
            "policy_version": self.policy_version,
            "model_versions": dict(self.model_versions),
            "reason": self.reason,
            "reviewed_at": self.reviewed_at,
            "average_score": self.average_score(),
        }


@dataclass(frozen=True)
class HumanSelectionOverride:
    """Audited human selection override (plan §25.5)."""

    override_id: str
    candidate_id: str
    actor: str
    decision: CandidateVerdict
    reason: str
    recorded_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "override_id": self.override_id,
            "candidate_id": self.candidate_id,
            "actor": self.actor,
            "decision": self.decision.value,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True)
class RetryProposal:
    """Which defect to fix + which request field changes (plan §25.5)."""

    candidate_id: str
    defects: Tuple[BlockingDefect, ...]
    request_field_changes: Tuple[str, ...]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "defects": [b.to_dict() for b in self.defects],
            "request_field_changes": list(self.request_field_changes),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SelectionRecord:
    """Deterministic selection among UNBLOCKED candidates (plan §25.5)."""

    selection_id: str
    run_id: str
    candidates_reviewed: Tuple[str, ...]
    ranked: Tuple[str, ...]  # eligible candidate ids, deterministic order
    selected_candidate_id: Optional[str]
    algorithm_version: str
    policy_version: str
    reason: str
    human_override: Optional[HumanSelectionOverride] = None
    retry_proposals: Tuple[RetryProposal, ...] = ()
    reviewed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "run_id": self.run_id,
            "candidates_reviewed": list(self.candidates_reviewed),
            "ranked": list(self.ranked),
            "selected_candidate_id": self.selected_candidate_id,
            "algorithm_version": self.algorithm_version,
            "policy_version": self.policy_version,
            "reason": self.reason,
            "human_override": self.human_override.to_dict() if self.human_override else None,
            "retry_proposals": [r.to_dict() for r in self.retry_proposals],
            "reviewed_at": self.reviewed_at,
        }


__all__ = [
    "ReviewDimension",
    "ReviewerType",
    "CandidateVerdict",
    "BlockingReasonCode",
    "DimensionResult",
    "BlockingDefect",
    "CandidateReview",
    "HumanSelectionOverride",
    "RetryProposal",
    "SelectionRecord",
]
