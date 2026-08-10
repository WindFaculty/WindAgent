"""
Canonical Studio approval model (studio.contract/v0.1).

``ApprovalPolicy`` v0.1 exposes: policy_id/version, checkpoint-to-mode map,
quality thresholds by checkpoint, max review/revision iterations, required
approver roles when human review is enabled, and effective time. An
``StudioApprovalDecision`` is bound to aggregate ID, revision ID, artifact hash,
checkpoint, actor, decision, reason, and timestamp. A stale hash or revision is
rejected by ``ApprovalPolicyService``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import EpisodeId, ProductionRevisionId
from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
from windagent_core.domain.studio.revision import StudioProductionRevision


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalDecisionValue(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalPolicy(BaseModel):
    """Quality-gate / human-approval policy for an episode's checkpoints."""

    model_config = ConfigDict(frozen=True, extra="allow")

    policy_id: str = Field(min_length=1)
    policy_version: str = "1"
    checkpoint_to_mode_map: Dict[ApprovalCheckpoint, ApprovalMode] = Field(
        default_factory=dict
    )
    quality_thresholds: Dict[ApprovalCheckpoint, float] = Field(default_factory=dict)
    max_review_revision_iterations: int = Field(default=10, ge=1)
    required_approver_roles: FrozenSet[str] = frozenset({"OWNER"})
    effective_time: datetime = Field(default_factory=utc_now)

    @field_validator("checkpoint_to_mode_map")
    @classmethod
    def _validate_checkpoints(cls, v: Dict[ApprovalCheckpoint, ApprovalMode]) -> Dict[ApprovalCheckpoint, ApprovalMode]:
        if not v:
            return v
        for checkpoint in v:
            if not isinstance(checkpoint, ApprovalCheckpoint):
                raise StudioValidationError(f"Unknown approval checkpoint {checkpoint!r}.")
        return v

    def mode_for(self, checkpoint: ApprovalCheckpoint) -> ApprovalMode:
        return self.checkpoint_to_mode_map.get(checkpoint, ApprovalMode.QUALITY_GATE_ONLY)

    def requires_human(self, checkpoint: ApprovalCheckpoint) -> bool:
        return self.mode_for(checkpoint) == ApprovalMode.HUMAN_REQUIRED

    def quality_threshold_for(self, checkpoint: ApprovalCheckpoint) -> Optional[float]:
        return self.quality_thresholds.get(checkpoint)


class StudioApprovalDecision(BaseModel):
    """Immutable approval decision bound to a specific revision + artifact hash."""

    model_config = ConfigDict(frozen=True, extra="allow")

    approval_id: str = Field(min_length=1)
    aggregate_id: EpisodeId
    revision_id: ProductionRevisionId
    artifact_hash: str = Field(min_length=64, max_length=64)
    checkpoint: ApprovalCheckpoint
    actor: str = Field(min_length=1)
    role: str = "OWNER"
    decision: ApprovalDecisionValue
    reason: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class ApprovalPolicyService:
    """Domain service enforcing approval binding and stale-write protection."""

    @staticmethod
    def record_decision(
        *,
        policy: Optional[ApprovalPolicy],
        revision: StudioProductionRevision,
        aggregate_id: EpisodeId,
        checkpoint: ApprovalCheckpoint,
        actor: str,
        decision: ApprovalDecisionValue,
        reason: str = "",
        role: str = "OWNER",
        submitted_artifact_hash: Optional[str] = None,
        expected_optimistic_version: Optional[int] = None,
    ) -> StudioApprovalDecision:
        """Create a decision, rejecting a stale hash or a stale revision."""
        if expected_optimistic_version is not None and (
            revision.optimistic_version != expected_optimistic_version
        ):
            raise StudioStaleRevisionError(
                "Cannot record approval against a stale revision.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_version": expected_optimistic_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if submitted_artifact_hash is not None and submitted_artifact_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Approval artifact hash does not match the canonical revision content hash.",
                details={
                    "revision_id": str(revision.revision_id),
                    "submitted_hash": submitted_artifact_hash,
                    "canonical_hash": revision.content_hash,
                },
            )
        if policy is not None and policy.requires_human(checkpoint) and role not in policy.required_approver_roles:
            raise StudioValidationError(
                f"Role {role!r} is not an allowed approver for {checkpoint.value}.",
                details={
                    "checkpoint": checkpoint.value,
                    "required_roles": sorted(policy.required_approver_roles),
                },
            )
        return StudioApprovalDecision(
            approval_id=f"appr_{revision.revision_id}_{checkpoint.value}_{actor}".lower(),
            aggregate_id=aggregate_id,
            revision_id=revision.revision_id,
            artifact_hash=revision.content_hash,
            checkpoint=checkpoint,
            actor=actor,
            role=role,
            decision=decision,
            reason=reason,
        )


__all__ = [
    "utc_now",
    "ApprovalDecisionValue",
    "ApprovalPolicy",
    "StudioApprovalDecision",
    "ApprovalPolicyService",
]
