"""Approval policy and decision (ported from the frozen studio contract)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .episodes.revision import ProductionRevision
from .errors import StudioArtifactHashMismatchError, StudioStaleRevisionError, StudioValidationError
from .lifecycle import ApprovalCheckpoint, ApprovalMode


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalDecisionValue(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(default="1")
    checkpoint_to_mode_map: dict[ApprovalCheckpoint, ApprovalMode] = Field(default_factory=dict)
    quality_thresholds: dict[ApprovalCheckpoint, float] = Field(default_factory=dict)
    max_review_revision_iterations: int = Field(default=10, ge=1)
    required_approver_roles: frozenset[str] = Field(default_factory=lambda: frozenset({"OWNER"}))
    effective_time: datetime = Field(default_factory=utc_now)

    def mode_for(self, checkpoint: ApprovalCheckpoint) -> ApprovalMode:
        return self.checkpoint_to_mode_map.get(checkpoint, ApprovalMode.QUALITY_GATE_ONLY)

    def requires_human(self, checkpoint: ApprovalCheckpoint) -> bool:
        return self.mode_for(checkpoint) == ApprovalMode.HUMAN_REQUIRED

    def quality_threshold_for(self, checkpoint: ApprovalCheckpoint) -> float | None:
        return self.quality_thresholds.get(checkpoint)


class StudioApprovalDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    approval_id: str = Field(min_length=1)
    aggregate_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    artifact_hash: str = Field(min_length=64, max_length=64)
    checkpoint: ApprovalCheckpoint
    actor: str = Field(min_length=1)
    role: str = Field(default="OWNER")
    decision: ApprovalDecisionValue
    reason: str = Field(default="")
    timestamp: datetime = Field(default_factory=utc_now)


class ApprovalPolicyService:
    @staticmethod
    def record_decision(
        *,
        policy: ApprovalPolicy | None,
        revision: ProductionRevision,
        aggregate_id: str,
        checkpoint: ApprovalCheckpoint,
        actor: str,
        decision: ApprovalDecisionValue,
        reason: str = "",
        role: str = "OWNER",
        submitted_artifact_hash: str | None = None,
        expected_optimistic_version: int | None = None,
    ) -> StudioApprovalDecision:
        if expected_optimistic_version is not None and revision.optimistic_version != expected_optimistic_version:
            raise StudioStaleRevisionError(
                "Cannot record approval against a stale revision.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_version": expected_optimistic_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if submitted_artifact_hash is not None and submitted_artifact_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Approval artifact hash does not match the canonical revision content hash.",
                context={
                    "revision_id": revision.revision_id,
                    "submitted_hash": submitted_artifact_hash,
                    "canonical_hash": revision.content_hash,
                },
            )
        if policy is not None and policy.requires_human(checkpoint) and role not in policy.required_approver_roles:
            raise StudioValidationError(
                f"Role {role!r} is not an allowed approver for {checkpoint.value}.",
                context={"checkpoint": checkpoint.value, "required_roles": sorted(policy.required_approver_roles)},
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
    "ApprovalDecisionValue",
    "ApprovalPolicy",
    "ApprovalPolicyService",
    "StudioApprovalDecision",
    "utc_now",
]

