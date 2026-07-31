"""
Review and approval models.

Approvals ALWAYS point at a specific revision + content hash and record the
actor, role, decision, reason, and timestamp. Approvals are idempotent: a
duplicate approval for the same target is not created (road_map.md Phase 20).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    ApprovalDecisionType,
    ApprovalRole,
    ReviewVerdict,
)
from windagent_core.domain.video_production.ids import (
    ApprovalId,
    GenerationCandidateId,
    ProductionRevisionId,
    ReviewResultId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewResult(BaseModel):
    """Multi-dimensional review of a generation candidate."""

    model_config = ConfigDict(frozen=True, extra="allow")

    review_id: ReviewResultId
    candidate_id: GenerationCandidateId
    dimensions: Dict[str, float] = Field(default_factory=dict)
    verdict: ReviewVerdict = ReviewVerdict.REQUIRES_HUMAN
    blocking_defects: List[str] = Field(default_factory=list)
    reviewer: str = ""
    reviewed_at: datetime = Field(default_factory=utc_now)


class ApprovalDecision(BaseModel):
    """Approval record bound to a specific revision + content hash."""

    model_config = ConfigDict(frozen=True, extra="allow")

    approval_id: ApprovalId
    project_id: str
    revision_id: ProductionRevisionId
    target_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1)
    role: ApprovalRole = ApprovalRole.OWNER
    decision: ApprovalDecisionType
    reason: str = ""
    decided_at: datetime = Field(default_factory=utc_now)


class ApprovalState(BaseModel):
    """Current approval state of a revision's package."""

    model_config = ConfigDict(frozen=True, extra="allow")

    approvals: List[ApprovalDecision] = Field(default_factory=list)
    locked: bool = False

    def has_approval_for_hash(self, target_hash: str) -> bool:
        return any(a.target_hash == target_hash and a.decision == ApprovalDecisionType.APPROVED
                   for a in self.approvals)


__all__ = [
    "utc_now",
    "ReviewResult",
    "ApprovalDecision",
    "ApprovalState",
]
