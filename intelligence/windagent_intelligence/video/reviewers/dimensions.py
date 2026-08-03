"""
Review dimension catalog (plan 05 Phase 20 §23, gate VP20_GENERATION_REVIEW_VERIFIED).

Each dimension declares:

- metric/check version;
- reviewer type (deterministic gate / VLM / cross-shot);
- PASS threshold;
- confidence floor (below it -> HUMAN_REVIEW_REQUIRED);
- whether the dimension is a BLOCKING rule (a failing blocking dimension
  always wins over any aggregate preference — plan §25.4).

The catalog is versioned (`REVIEW_POLICY_VERSION`): a threshold or policy
change MUST produce a new version — old review results are never rewritten
(plan §26 "Policy/threshold change làm review revision mới, không sửa result
cũ").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from windagent_intelligence.video.reviewers.models import (
    ReviewDimension,
    ReviewerType,
)

REVIEW_POLICY_VERSION = "1.0.0"


@dataclass(frozen=True)
class DimensionConfig:
    """Configuration for one review dimension (plan §23)."""

    dimension: ReviewDimension
    reviewer_type: ReviewerType
    pass_threshold: float  # score >= threshold => dimension passes
    confidence_floor: float  # confidence < floor => human review
    blocking: bool = False


REVIEW_DIMENSIONS: Dict[ReviewDimension, DimensionConfig] = {
    ReviewDimension.TECHNICAL_VALIDITY: DimensionConfig(
        dimension=ReviewDimension.TECHNICAL_VALIDITY,
        reviewer_type=ReviewerType.DETERMINISTIC,
        pass_threshold=1.0,
        confidence_floor=1.0,
        blocking=True,
    ),
    ReviewDimension.SAFETY: DimensionConfig(
        dimension=ReviewDimension.SAFETY,
        reviewer_type=ReviewerType.DETERMINISTIC,
        pass_threshold=1.0,
        confidence_floor=1.0,
        blocking=True,
    ),
    ReviewDimension.PROMPT_COMPLIANCE: DimensionConfig(
        dimension=ReviewDimension.PROMPT_COMPLIANCE,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.7,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.IDENTITY_CONSISTENCY: DimensionConfig(
        dimension=ReviewDimension.IDENTITY_CONSISTENCY,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.7,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.LOCATION_CONSISTENCY: DimensionConfig(
        dimension=ReviewDimension.LOCATION_CONSISTENCY,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.7,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.PROP_CONSISTENCY: DimensionConfig(
        dimension=ReviewDimension.PROP_CONSISTENCY,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.7,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.CONTINUITY: DimensionConfig(
        dimension=ReviewDimension.CONTINUITY,
        reviewer_type=ReviewerType.CROSS_SHOT,
        pass_threshold=1.0,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.MOTION_QUALITY: DimensionConfig(
        dimension=ReviewDimension.MOTION_QUALITY,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.6,
        confidence_floor=0.6,
        blocking=False,
    ),
    ReviewDimension.CAMERA_COMPLIANCE: DimensionConfig(
        dimension=ReviewDimension.CAMERA_COMPLIANCE,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.7,
        confidence_floor=0.6,
        blocking=True,
    ),
    ReviewDimension.DIALOGUE_ALIGNMENT: DimensionConfig(
        dimension=ReviewDimension.DIALOGUE_ALIGNMENT,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.6,
        confidence_floor=0.6,
        blocking=False,
    ),
    ReviewDimension.VISUAL_ARTIFACTS: DimensionConfig(
        dimension=ReviewDimension.VISUAL_ARTIFACTS,
        reviewer_type=ReviewerType.VLM,
        pass_threshold=0.6,
        confidence_floor=0.6,
        blocking=False,
    ),
}

BLOCKING_DIMENSIONS = frozenset(
    d for d, cfg in REVIEW_DIMENSIONS.items() if cfg.blocking
)


def config_for(dimension: ReviewDimension) -> DimensionConfig:
    """Return the catalog config; unknown dimension fails closed."""
    if dimension not in REVIEW_DIMENSIONS:
        raise ValueError(f"Unknown review dimension {dimension}")
    return REVIEW_DIMENSIONS[dimension]


__all__ = [
    "REVIEW_POLICY_VERSION",
    "DimensionConfig",
    "REVIEW_DIMENSIONS",
    "BLOCKING_DIMENSIONS",
    "config_for",
]
