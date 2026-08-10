"""
Plan B review/revision/lock content models (studio.artifact/v1alpha1): S9-S10.

- ``ReviewReport`` — aggregated findings + quality verdict over one draft.
- ``RevisionProposal`` — references exact reviewed draft and accepted findings.
- ``StoryDiff`` — structural/semantic diff between two immutable drafts.
- ``LockedScreenplayReceipt`` — A-issued authority for the lock transition.
- ``LockedScreenplayPackage`` — immutable package referencing approved
  artifacts by ``(artifact_id, content_hash, revision_id)`` plus manifest;
  never embeds a mutable draft as authority (rule 7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ids import (
    LockedScreenplayPackageId,
    LockedScreenplayReceiptId,
    ReviewReportId,
    RevisionProposalId,
    ScreenplayDraftId,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationSeverity,
)

__all__ = [
    "ReviewFinding",
    "DimensionResult",
    "ReviewReport",
    "RevisionProposal",
    "StoryDiff",
    "SceneChange",
    "DialogueChange",
    "LockedScreenplayReceipt",
    "LockedScreenplayPackage",
    "PackageArtifactRef",
    "READY_FOR_PRODUCTION",
]

READY_FOR_PRODUCTION = "READY_FOR_PRODUCTION"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewFinding(BaseModel):
    """One review finding (frozen shape from the B0 taxonomy)."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    severity: ValidationSeverity = ValidationSeverity.WARNING
    location: str = ""
    evidence: str = ""
    remediation: str = ""
    source: str = "deterministic"  # deterministic | model | human
    dimension: Optional[str] = None


class DimensionResult(BaseModel):
    """One quality dimension outcome inside a review report."""

    model_config = ConfigDict(frozen=True)

    dimension: str
    score: float = Field(ge=0.0, le=1.0)
    blocking: bool = False
    note: str = ""


class ReviewReport(StoryContent):
    """Aggregated, explainable review of one screenplay draft."""

    artifact_type: str = "ReviewReport"
    report_id: ReviewReportId
    draft_id: ScreenplayDraftId
    review_iteration: int = Field(default=1, ge=1)
    findings: List[ReviewFinding] = Field(default_factory=list)
    dimensions: List[DimensionResult] = Field(default_factory=list)
    verdict: str = "REVIEW_REQUIRED"  # PASS | PASS_WITH_WARNINGS | REVIEW_REQUIRED | FAIL
    quality_summary: str = ""
    maximum_iterations: int = Field(default=3, ge=1)

    SUMMARY_FIELDS = (
        "artifact_type", "report_id", "draft_id", "review_iteration",
        "verdict", "quality_summary", "finding_count",
    )

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def blocking_findings(self) -> List[ReviewFinding]:
        return [f for f in self.findings if f.severity == ValidationSeverity.BLOCKING]

    @property
    def is_pass(self) -> bool:
        return self.verdict in ("PASS", "PASS_WITH_WARNINGS") and not self.blocking_findings

    def to_summary(self) -> dict:
        data = super().to_summary()
        data["finding_count"] = self.finding_count
        data["blocking_count"] = len(self.blocking_findings)
        return data


class RevisionProposal(StoryContent):
    """Bounded revision request bound to a reviewed draft and its findings."""

    artifact_type: str = "RevisionProposal"
    proposal_id: RevisionProposalId
    draft_id: ScreenplayDraftId
    review_report_id: ReviewReportId
    accepted_finding_codes: List[str] = Field(default_factory=list)
    revision_reason: str = Field(min_length=1)
    iteration_number: int = Field(default=1, ge=1)
    maximum_iterations: int = Field(default=3, ge=1)

    SUMMARY_FIELDS = (
        "artifact_type", "proposal_id", "draft_id", "review_report_id",
        "iteration_number", "maximum_iterations", "revision_reason",
    )

    @property
    def budget_exhausted(self) -> bool:
        return self.iteration_number >= self.maximum_iterations


class SceneChange(BaseModel):
    """One scene-level structural change between two drafts."""

    model_config = ConfigDict(frozen=True)

    scene_id: str
    kind: str  # ADDED | DELETED | MODIFIED | REORDERED
    detail: str = ""


class DialogueChange(BaseModel):
    """One dialogue-level change between two drafts."""

    model_config = ConfigDict(frozen=True)

    dialogue_id: str
    scene_id: str
    kind: str  # ADDED | DELETED | MODIFIED
    detail: str = ""


class StoryDiff(StoryContent):
    """Structural/semantic diff between two immutable drafts (never mutates)."""

    artifact_type: str = "StoryDiff"
    from_draft_id: ScreenplayDraftId
    to_draft_id: ScreenplayDraftId
    scene_changes: List[SceneChange] = Field(default_factory=list)
    dialogue_changes: List[DialogueChange] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)  # kind -> count

    SUMMARY_FIELDS = ("artifact_type", "from_draft_id", "to_draft_id", "summary")

    @property
    def is_empty(self) -> bool:
        return not self.scene_changes and not self.dialogue_changes


class LockedScreenplayReceipt(StoryContent):
    """A-issued authority for the READY_FOR_PRODUCTION lock transition."""

    artifact_type: str = "LockedScreenplayReceipt"
    receipt_id: LockedScreenplayReceiptId
    draft_id: ScreenplayDraftId
    state: str = READY_FOR_PRODUCTION
    approval_mode: str = ""
    policy_id: str = ""
    issued_at: datetime = Field(default_factory=utc_now)

    SUMMARY_FIELDS = (
        "artifact_type", "receipt_id", "draft_id", "state",
        "approval_mode", "policy_id", "issued_at",
    )


class PackageArtifactRef(BaseModel):
    """Manifest entry: immutable reference to an approved artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_type: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    revision_id: Optional[str] = None


class LockedScreenplayPackage(StoryContent):
    """Immutable lock-ready package: manifest of approved artifact refs.

    The manifest IS the content: it references immutable approved artifacts by
    ``(artifact_id, content_hash, revision_id)`` and never copies a mutable
    in-memory draft as authority (cross-cutting rule 7).
    """

    artifact_type: str = "LockedScreenplayPackage"
    package_id: LockedScreenplayPackageId
    receipt_id: LockedScreenplayReceiptId
    title: str = Field(min_length=1)
    manifest: List[PackageArtifactRef] = Field(default_factory=list)
    assembled_at: datetime = Field(default_factory=utc_now)

    SUMMARY_FIELDS = (
        "artifact_type", "package_id", "receipt_id", "title",
        "manifest_count", "assembled_at",
    )

    @property
    def manifest_count(self) -> int:
        return len(self.manifest)

    def to_summary(self) -> dict:
        data = super().to_summary()
        data["manifest_count"] = self.manifest_count
        data["manifest_types"] = [m.artifact_type for m in self.manifest]
        return data
