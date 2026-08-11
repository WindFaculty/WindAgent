"""Plan B B7 review/revision pipeline services (S9).

- ``ReviewService`` — deterministic review over one ``ScreenplayDraft``
  (format/duration/canon/continuity/beat coverage from the validation suite,
  mapped to stable finding codes/dimensions) plus a model-assisted narrative
  review that is strictly SECONDARY (scores below the published threshold
  become warning findings; the deterministic suite stays the gate authority).
  Aggregates findings, computes dimension scores and the verdict, and
  validates the assembled ``ReviewReport``.
- ``ReviseService`` — bounded revision: validates the proposal binding to
  the reviewed report/draft, invokes ``story.revise.rewrite`` for a NEW
  immutable draft, re-validates it, and produces the structural diff. Never
  mutates the reviewed draft; the iteration budget stops the loop
  deterministically (separate from provider retries).
- ``LockService`` — S10 lock assembly: validates approval policy/checkpoint,
  review threshold, iteration status, and complete lineage, then assembles
  the immutable ``LockedScreenplayPackage`` from A-issued refs
  ``(artifact_id, content_hash, revision_id)`` — never copied mutable state.
  The A-issued ``LockedScreenplayReceipt`` is the authority; the A atomic
  lock transition itself stays an A checkpoint command outside this service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.story.bibles import CharacterCanon, WorldBible
from windagent_core.domain.story.ids import (
    LockedScreenplayPackageId,
    ReviewReportId,
    RevisionProposalId,
)
from windagent_core.domain.story.outline import BeatSheet, EpisodeOutline
from windagent_core.domain.story.review import (
    READY_FOR_PRODUCTION,
    DimensionResult,
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewFinding,
    ReviewReport,
    RevisionProposal,
    StoryDiff,
    aggregate_findings,
    build_story_diff,
    REQUIRED_PACKAGE_ARTIFACTS,
    validate_locked_package,
    validate_review_report,
    validate_revision_proposal,
    validate_story_diff,
)
from windagent_core.domain.story.screenplay import (
    ScreenplayDraft,
    validate_screenplay_draft,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationSeverity,
    ValidationSource,
)
from windagent_intelligence.story.prompts import (
    StoryModelBoundary,
    StoryModelProvenance,
)

__all__ = [
    "REVIEW_POLICY_VERSION",
    "LOCK_POLICY_VERSION",
    "APPROVAL_MODES",
    "DIMENSION_THRESHOLD",
    "DEFAULT_MAXIMUM_ITERATIONS",
    "ReviewValidationFailure",
    "ReviseValidationFailure",
    "LockValidationFailure",
    "ReviewResult",
    "RevisionResult",
    "LockResult",
    "ReviewService",
    "ReviseService",
    "LockService",
]

REVIEW_POLICY_VERSION = "review_policy/v1"
LOCK_POLICY_VERSION = "lock_policy/v1"
DIMENSION_THRESHOLD = 0.5
DEFAULT_MAXIMUM_ITERATIONS = 3

#: Approval modes that can produce an A-issued lock receipt (studio lifecycle).
APPROVAL_MODES = frozenset({"AUTO", "HUMAN_REQUIRED", "QUALITY_GATE_ONLY"})

_MODEL_DIMENSIONS = (
    ("narrative_score", "narrative"),
    ("age_fit_score", "age_fit"),
    ("language_score", "language"),
)

_DIMENSION_BY_CODE = {
    "ID_UNIQUE": "format",
    "ORDER_SEQUENCE": "format",
    "ID_STABILITY": "format",
    "DIALOGUE_ATTRIBUTION": "format",
    "DIALOGUE_EMPTY": "format",
    "FIELD_EMPTY": "format",
    "FIELD_TOO_LONG": "format",
    "FORMAT_VALIDITY": "format",
    "DURATION_BOUND": "duration",
    "DURATION_SUM": "duration",
    "REF_MISSING": "continuity",
    "BEAT_COVERAGE": "beat_coverage",
}

_REMEDIATION_BY_CODE = {
    "FIELD_EMPTY": "Add action, dialogue, or narration to the scene.",
    "DIALOGUE_ATTRIBUTION": "Assign the line to a character in the scene cast.",
    "ID_STABILITY": "Bind the dialogue line to the scene that stores it.",
    "DIALOGUE_EMPTY": "Give the dialogue line non-empty text.",
    "ORDER_SEQUENCE": "Renumber scenes/dialogue as unique 1..N.",
    "ID_UNIQUE": "Use distinct scene ids.",
    "REF_MISSING": "Reference only known canon/outline ids.",
    "BEAT_COVERAGE": "Cover every beat; reference only known beats.",
    "DURATION_BOUND": "Fit the total inside 180-300 seconds.",
    "DURATION_SUM": "Bring the total within tolerance of the target.",
    "FORMAT_VALIDITY": "Use a transition from the frozen vocabulary.",
    "MODEL_DIMENSION_SCORE": "Improve the flagged narrative dimension in the next revision.",
}


class ReviewValidationFailure(StudioValidationError):
    """Review output could not produce a valid report (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


class ReviseValidationFailure(StudioValidationError):
    """Revision was refused (stale/budget/identical) or output failed (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


class LockValidationFailure(StudioValidationError):
    """Lock was refused (stale receipt/approval/hash/lineage) or package failed (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


@dataclass(frozen=True)
class ReviewResult:
    report: ReviewReport
    model_provenance: Optional[StoryModelProvenance]
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report": self.report.to_canonical_dict(),
            "validation": self.validation,
            "model_provenance": (
                self.model_provenance.to_dict() if self.model_provenance else None
            ),
        }


@dataclass(frozen=True)
class RevisionResult:
    new_draft: ScreenplayDraft
    proposal: RevisionProposal
    diff: StoryDiff
    provenance: StoryModelProvenance
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "new_draft": self.new_draft.to_canonical_dict(),
            "proposal": self.proposal.to_canonical_dict(),
            "diff": self.diff.to_canonical_dict(),
            "validation": self.validation,
            "provenance": self.provenance.to_dict(),
        }


def _scene_summary(draft: ScreenplayDraft) -> str:
    lines = []
    for scene in draft.scenes:
        dialogue = "; ".join(
            f"{line.character_id.value}: {line.text[:60]}" for line in scene.dialogue
        )
        lines.append(
            f"- {scene.scene_id.value}|outline {scene.outline_scene_id.value}"
            f"|{scene.location_id.value}|{scene.estimated_seconds}s"
            f"|beats {','.join(b.value for b in scene.source_beat_ids)}"
            f"|{scene.action_description[:80]}"
            + (f"|{dialogue}" if dialogue else "")
        )
    return "\n".join(lines)


def _findings_summary(findings: List[ReviewFinding]) -> str:
    return "\n".join(
        f"- [{f.severity.value}] {f.code} @{f.location}: {f.evidence}"
        for f in findings
    )


class ReviewService:
    """Deterministic + model-assisted review of one immutable draft."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        draft: ScreenplayDraft,
        *,
        outline: Optional[EpisodeOutline] = None,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        review_iteration: int = 1,
        maximum_iterations: int = DEFAULT_MAXIMUM_ITERATIONS,
        quality_threshold: Optional[float] = None,
        route_lock_id: Optional[str] = None,
    ) -> ReviewResult:
        deterministic_report = validate_screenplay_draft(
            draft,
            outline=outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
        )
        findings: List[ReviewFinding] = [
            ReviewFinding(
                code=issue.code,
                severity=issue.severity,
                location=issue.location,
                evidence=issue.evidence,
                remediation=_REMEDIATION_BY_CODE.get(issue.code, ""),
                source="deterministic",
                dimension=_DIMENSION_BY_CODE.get(issue.code, "structure"),
            )
            for issue in deterministic_report.issues
        ]

        result = await self.boundary.invoke(
            "story.review.assess",
            variables={
                "title": draft.title,
                "logline": draft.logline,
                "language": draft.language,
                "audience_band": draft.audience_band,
                "target_duration_seconds": draft.target_duration_seconds,
                "total_estimated_seconds": draft.total_estimated_seconds,
                "scene_count": draft.scene_count,
                "dialogue_count": draft.dialogue_count,
                "scene_summary": _scene_summary(draft),
                "deterministic_findings": _findings_summary(findings) or "none",
            },
            route_lock_id=route_lock_id,
        )
        data = result.data

        applied_threshold = (
            quality_threshold if quality_threshold is not None else DIMENSION_THRESHOLD
        )
        model_provenance = result.provenance.to_dict()
        for field, dimension in _MODEL_DIMENSIONS:
            score = float(data[field])
            if score < applied_threshold:
                findings.append(ReviewFinding(
                    code=(
                        "QUALITY_THRESHOLD_VIOLATION"
                        if quality_threshold is not None
                        else "MODEL_DIMENSION_SCORE"
                    ),
                    severity=(
                        ValidationSeverity.BLOCKING
                        if quality_threshold is not None
                        else ValidationSeverity.WARNING
                    ),
                    location=f"dimensions/{dimension}",
                    evidence=f"{dimension} score {score} below threshold {applied_threshold}",
                    remediation=_REMEDIATION_BY_CODE["MODEL_DIMENSION_SCORE"],
                    source="model",
                    dimension=dimension,
                    threshold=applied_threshold,
                    actual_score=score,
                    provenance=model_provenance,
                ))

        findings = aggregate_findings(findings)
        dimensions = self._dimensions(
            findings,
            data,
            quality_threshold=quality_threshold,
            applied_threshold=applied_threshold,
        )

        blocking = [f for f in findings if f.severity == ValidationSeverity.BLOCKING]
        warnings = [f for f in findings if f.severity == ValidationSeverity.WARNING]
        if blocking:
            verdict = "REVIEW_REQUIRED"
        elif warnings:
            verdict = "PASS_WITH_WARNINGS"
        else:
            verdict = "PASS"

        report = ReviewReport(
            report_id=ReviewReportId(f"report_{draft.draft_id.value}_{review_iteration}_{verdict.lower()}"),
            draft_id=draft.draft_id,
            review_iteration=review_iteration,
            findings=findings,
            dimensions=dimensions,
            verdict=verdict,
            quality_summary=(
                f"{len(findings)} findings ({len(blocking)} blocking, {len(warnings)} "
                f"warnings); policy {REVIEW_POLICY_VERSION}, dimension threshold "
                f"{applied_threshold}."
            ),
            maximum_iterations=maximum_iterations,
        )
        report_validation = validate_review_report(report)
        if not report_validation.is_pass():
            raise ReviewValidationFailure(
                "ReviewReport failed its own validation.",
                details={"issues": [i.to_dict() for i in report_validation.issues]},
            )
        return ReviewResult(
            report=report,
            model_provenance=result.provenance,
            validation=report_validation.summary(),
        )

    @staticmethod
    def _dimensions(
        findings: List[ReviewFinding],
        model_data: Dict[str, Any],
        *,
        quality_threshold: Optional[float],
        applied_threshold: float,
    ) -> List[DimensionResult]:
        dimensions: List[DimensionResult] = []
        by_dimension: Dict[str, List[ReviewFinding]] = {}
        for finding in findings:
            if finding.dimension and finding.source == "deterministic":
                by_dimension.setdefault(finding.dimension, []).append(finding)
        for dimension, dim_findings in sorted(by_dimension.items()):
            has_blocking = any(
                f.severity == ValidationSeverity.BLOCKING for f in dim_findings
            )
            has_warnings = any(
                f.severity == ValidationSeverity.WARNING for f in dim_findings
            )
            score = 0.0 if has_blocking else (0.8 if has_warnings else 1.0)
            dimensions.append(DimensionResult(
                dimension=dimension,
                score=score,
                blocking=has_blocking,
                note=", ".join(sorted({f.code for f in dim_findings})),
            ))
        for field, dimension in _MODEL_DIMENSIONS:
            score = float(model_data[field])
            dimensions.append(DimensionResult(
                dimension=dimension,
                score=score,
                blocking=quality_threshold is not None and score < applied_threshold,
                note="model-assisted (secondary)",
            ))
        return dimensions


class ReviseService:
    """Bounded revision: NEW immutable draft + proposal + structural diff."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        draft: ScreenplayDraft,
        report: ReviewReport,
        *,
        outline: Optional[EpisodeOutline] = None,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        tolerance_seconds: int = 15,
        route_lock_id: Optional[str] = None,
    ) -> RevisionResult:
        if not report.findings:
            raise ReviseValidationFailure(
                "Nothing to revise: the review report has no findings.",
                details={"draft_id": str(draft.draft_id), "report_id": str(report.report_id)},
            )
        next_iteration = report.review_iteration + 1
        if next_iteration > report.maximum_iterations:
            raise ReviseValidationFailure(
                "Revision budget exhausted; the loop stops deterministically.",
                details={
                    "next_iteration": next_iteration,
                    "maximum_iterations": report.maximum_iterations,
                },
            )
        proposal = RevisionProposal(
            proposal_id=RevisionProposalId(f"proposal_{draft.draft_id.value}_{next_iteration}"),
            draft_id=draft.draft_id,
            review_report_id=report.report_id,
            accepted_finding_codes=sorted({f.code for f in report.findings}),
            revision_reason=(
                f"Address {len(report.findings)} finding(s) from review "
                f"{report.report_id} (iteration {next_iteration}/{report.maximum_iterations})."
            ),
            iteration_number=next_iteration,
            maximum_iterations=report.maximum_iterations,
        )
        proposal_validation = validate_revision_proposal(proposal, report)
        if not proposal_validation.is_pass():
            raise ReviseValidationFailure(
                "RevisionProposal failed its own validation.",
                details={"issues": [i.to_dict() for i in proposal_validation.issues]},
            )

        result = await self.boundary.invoke(
            "story.revise.rewrite",
            variables={
                "title": draft.title,
                "language": language,
                "audience_band": audience_band,
                "target_duration_seconds": draft.target_duration_seconds,
                "tolerance_seconds": tolerance_seconds,
                "total_estimated_seconds": draft.total_estimated_seconds,
                "scene_summary": _scene_summary(draft),
                "findings_summary": _findings_summary(report.findings),
                "old_draft_id": draft.draft_id.value,
            },
            route_lock_id=route_lock_id,
        )
        new_draft = ScreenplayDraft(**result.data)
        if new_draft.draft_id == draft.draft_id:
            raise ReviseValidationFailure(
                "Revision must produce a NEW draft id; the reviewed draft is immutable.",
                details={"old_draft_id": draft.draft_id.value},
            )
        new_validation = validate_screenplay_draft(
            new_draft,
            outline=outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
        )
        if not new_validation.is_pass():
            raise ReviseValidationFailure(
                "Revised ScreenplayDraft failed validation; never persisted as approved.",
                details={"issues": [i.to_dict() for i in new_validation.issues]},
            )
        diff = build_story_diff(draft, new_draft)
        diff_validation = validate_story_diff(diff)
        if not diff_validation.is_pass():
            raise ReviseValidationFailure(
                "StoryDiff failed validation.",
                details={"issues": [i.to_dict() for i in diff_validation.issues]},
            )
        if diff.is_empty:
            raise ReviseValidationFailure(
                "Revision produced no structural change; refusing an empty revision.",
                details={"from_draft_id": draft.draft_id.value, "to_draft_id": new_draft.draft_id.value},
            )
        return RevisionResult(
            new_draft=new_draft,
            proposal=proposal,
            diff=diff,
            provenance=result.provenance,
            validation=new_validation.summary(),
        )


@dataclass(frozen=True)
class LockResult:
    """Outcome of a lock assembly: the A-issued receipt + the immutable package."""

    receipt: LockedScreenplayReceipt
    package: LockedScreenplayPackage
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt": self.receipt.to_canonical_dict(),
            "package": self.package.to_canonical_dict(),
            "package_content_hash": self.package.content_hash(),
            "package_summary": self.package.to_summary(),
            "validation": self.validation,
        }


class LockService:
    """S10 lock assembly: approval/lineage validation + immutable package.

    Deterministic and provider-free. The A-issued ``LockedScreenplayReceipt``
    is the authority; this service validates it (state, approval mode,
    policy binding, draft binding), validates the review threshold and
    iteration status, verifies every lineage ref hash against the live
    canonical content, and assembles ``LockedScreenplayPackage`` from the
    immutable refs — never from copied mutable state (rule 7). The A atomic
    lock transition (``READY_FOR_PRODUCTION``) is requested by A's
    orchestrator command outside this service; post-lock mutation is refused
    here by hash binding and requires a derived revision instead.
    """

    def assemble(
        self,
        *,
        draft: ScreenplayDraft,
        report: ReviewReport,
        receipt: LockedScreenplayReceipt,
        lineage_refs: List[PackageArtifactRef],
        title: Optional[str] = None,
    ) -> LockResult:
        issues = self._validate(draft, report, receipt, lineage_refs)
        if issues:
            raise LockValidationFailure(
                "Lock refused: approval/lineage validation failed.",
                details={
                    "policy": LOCK_POLICY_VERSION,
                    "issues": [i.to_dict() for i in issues],
                },
            )

        refs_by_type = {r.artifact_type: r for r in lineage_refs}
        manifest = sorted(refs_by_type.values(), key=lambda r: (r.artifact_type, r.artifact_id))
        package = LockedScreenplayPackage(
            package_id=LockedScreenplayPackageId(
                f"pkg_{receipt.receipt_id.value}_{draft.draft_id.value}"
            ),
            receipt_id=receipt.receipt_id,
            title=title or draft.title,
            manifest=manifest,
            # Deterministic: the package binds to the receipt instant, so the
            # same inputs always assemble to the same immutable package.
            assembled_at=receipt.issued_at,
        )
        package_validation = validate_locked_package(package, receipt)
        if not package_validation.is_pass():
            raise LockValidationFailure(
                "Assembled LockedScreenplayPackage failed validation.",
                details={"issues": [i.to_dict() for i in package_validation.issues]},
            )
        return LockResult(
            receipt=receipt,
            package=package,
            validation=package_validation.summary(),
        )

    def _validate(
        self,
        draft: ScreenplayDraft,
        report: ReviewReport,
        receipt: LockedScreenplayReceipt,
        lineage_refs: List[PackageArtifactRef],
    ) -> List[Any]:
        """Deterministic refusal checks; returns blocking issues (typed)."""
        issues: List[Any] = []

        def _issue(code: str, location: str, evidence: str) -> ValidationIssue:
            return ValidationIssue(
                code=code,
                severity=ValidationSeverity.BLOCKING,
                location=location,
                evidence=evidence,
                source=ValidationSource.DETERMINISTIC,
            )

        # 1. Receipt authority: state, draft binding, approval mode/policy.
        if receipt.state != READY_FOR_PRODUCTION:
            issues.append(_issue(
                "LOCK_STATE", "receipt/state",
                f"receipt state {receipt.state!r} is not {READY_FOR_PRODUCTION}",
            ))
        if receipt.draft_id != draft.draft_id:
            issues.append(_issue(
                "RECEIPT_DRAFT_MISMATCH", "receipt/draft_id",
                f"receipt binds draft {receipt.draft_id} but lock targets {draft.draft_id}",
            ))
        if receipt.approval_mode not in APPROVAL_MODES:
            issues.append(_issue(
                "APPROVAL_MODE", "receipt/approval_mode",
                f"unknown approval mode {receipt.approval_mode!r}",
            ))
        if receipt.approval_mode == "HUMAN_REQUIRED" and not receipt.policy_id:
            issues.append(_issue(
                "APPROVAL_POLICY", "receipt/policy_id",
                "HUMAN_REQUIRED lock must bind an approval policy id",
            ))

        # 2. Review threshold + iteration status (final report authority).
        if report.draft_id != draft.draft_id:
            issues.append(_issue(
                "REVIEW_STALE", "report/draft_id",
                f"report reviews {report.draft_id} but lock targets {draft.draft_id}",
            ))
        if not report.is_pass:
            issues.append(_issue(
                "REVIEW_THRESHOLD", "report/verdict",
                f"verdict {report.verdict!r} is not PASS/PASS_WITH_WARNINGS or has blocking findings",
            ))
        if receipt.approval_mode == "AUTO" and report.verdict != "PASS":
            issues.append(_issue(
                "APPROVAL_MODE", "report/verdict",
                "AUTO approval requires a clean PASS (no warnings)",
            ))
        if report.review_iteration > report.maximum_iterations:
            issues.append(_issue(
                "REVISION_BUDGET", "report/review_iteration",
                f"iteration {report.review_iteration} exceeds maximum {report.maximum_iterations}",
            ))

        # 3. Complete lineage: required types present, no duplicates, hash binding.
        refs_by_type: Dict[str, PackageArtifactRef] = {}
        seen_ids: List[str] = []
        for ref in lineage_refs:
            if ref.artifact_id in seen_ids:
                issues.append(_issue(
                    "MANIFEST_DUPLICATE", f"manifest/{ref.artifact_type}",
                    f"duplicate lineage ref {ref.artifact_id}",
                ))
            seen_ids.append(ref.artifact_id)
            refs_by_type[ref.artifact_type] = ref
        missing = sorted(REQUIRED_PACKAGE_ARTIFACTS - set(refs_by_type))
        if missing:
            issues.append(_issue(
                "MANIFEST_MISSING_REF", "manifest",
                f"lineage incomplete; missing artifact types: {missing}",
            ))
        for model, artifact_type in (
            (draft, "ScreenplayDraft"),
            (report, "ReviewReport"),
            (receipt, "LockedScreenplayReceipt"),
        ):
            ref = refs_by_type.get(artifact_type)
            if ref is None:
                continue
            live_hash = model.content_hash()
            if ref.content_hash != live_hash:
                issues.append(_issue(
                    "HASH_MISMATCH", f"manifest/{artifact_type}",
                    f"A ref hash {ref.content_hash[:16]}… != live canonical hash "
                    f"{live_hash[:16]}… (post-lock mutation requires a derived revision)",
                ))
        return issues
