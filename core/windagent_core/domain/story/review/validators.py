"""
Deterministic review/revision/lock validators (Plan B B7/B8).

Finding aggregation/dedup/order, verdict consistency, revision proposal
binding, diff correctness, and locked-package lineage. No provider, no hidden
mutation; the review loop never runs forever (iteration budget is separate
from provider retries).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from windagent_core.domain.story.review.models import (
    READY_FOR_PRODUCTION,
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewFinding,
    ReviewReport,
    RevisionProposal,
    SceneChange,
    StoryDiff,
)
from windagent_core.domain.story.screenplay.models import ScreenplayDraft
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    ValidationSource,
    json_pointer,
)

__all__ = [
    "aggregate_findings",
    "validate_review_report",
    "validate_revision_proposal",
    "validate_story_diff",
    "validate_locked_package",
    "build_story_diff",
]

REQUIRED_PACKAGE_ARTIFACTS = {
    "ScreenplayDraft",
    "ReviewReport",
    "LockedScreenplayReceipt",
    "SelectedIdea",
    "StoryBible",
    "WorldBible",
    "CharacterCanon",
    "BeatSheet",
    "EpisodeOutline",
}


def _issue(
    code: str,
    location: str,
    evidence: str,
    severity: ValidationSeverity = ValidationSeverity.BLOCKING,
) -> ValidationIssue:
    return ValidationIssue(
        code=code, severity=severity, location=location, evidence=evidence,
        source=ValidationSource.DETERMINISTIC,
    )


def aggregate_findings(findings: List[ReviewFinding]) -> List[ReviewFinding]:
    """Deterministic aggregation: dedup by (code, location), severity order."""
    seen: Dict[Tuple[str, str], ReviewFinding] = {}
    for finding in findings:
        key = (finding.code, finding.location)
        if key not in seen:
            seen[key] = finding
    ranked = sorted(
        seen.values(),
        key=lambda f: (
            {"BLOCKING": 0, "WARNING": 1, "INFO": 2}[f.severity.value],
            f.code,
            f.location,
        ),
    )
    return ranked


def validate_review_report(report: ReviewReport) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if report.blocking_findings and report.verdict in ("PASS", "PASS_WITH_WARNINGS"):
        issues.append(_issue(
            "REVIEW_VERDICT", json_pointer("verdict"),
            f"verdict {report.verdict} with {len(report.blocking_findings)} blocking findings",
        ))
    if report.verdict not in ("PASS", "PASS_WITH_WARNINGS", "REVIEW_REQUIRED", "FAIL"):
        issues.append(_issue(
            "REVIEW_VERDICT", json_pointer("verdict"),
            f"unknown verdict {report.verdict!r}",
        ))
    if report.maximum_iterations < 1:
        issues.append(_issue(
            "REVISION_BUDGET", json_pointer("maximum_iterations"),
            "maximum_iterations must be >= 1",
        ))
    return ValidationReport(artifact_type=report.artifact_type, issues=issues)


def validate_revision_proposal(
    proposal: RevisionProposal,
    report: ReviewReport | None = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if report is None:
        return ValidationReport(artifact_type=proposal.artifact_type, issues=issues)
    if proposal.draft_id != report.draft_id:
        issues.append(_issue(
            "REVISION_STALE", json_pointer("draft_id"),
            f"proposal targets draft {proposal.draft_id} but report reviews {report.draft_id}",
        ))
    if proposal.review_report_id != report.report_id:
        issues.append(_issue(
            "REVISION_STALE", json_pointer("review_report_id"),
            "proposal references a different review report",
        ))
    report_codes = {f.code for f in report.findings}
    unknown = [c for c in proposal.accepted_finding_codes if c not in report_codes]
    if unknown:
        issues.append(_issue(
            "REVISION_STALE", json_pointer("accepted_finding_codes"),
            f"accepted findings not in reviewed report: {unknown}",
        ))
    if proposal.iteration_number > proposal.maximum_iterations:
        issues.append(_issue(
            "REVISION_BUDGET", json_pointer("iteration_number"),
            f"iteration {proposal.iteration_number} exceeds maximum {proposal.maximum_iterations}",
        ))
    return ValidationReport(artifact_type=proposal.artifact_type, issues=issues)


def build_story_diff(
    from_draft: ScreenplayDraft,
    to_draft: ScreenplayDraft,
) -> StoryDiff:
    """Deterministic structural diff; never mutates either draft."""
    scene_changes: List[SceneChange] = []
    from_scenes = {s.scene_id: s for s in from_draft.scenes}
    to_scenes = {s.scene_id: s for s in to_draft.scenes}

    for scene_id in from_scenes.keys() - to_scenes.keys():
        scene_changes.append(SceneChange(scene_id=scene_id.value, kind="DELETED"))
    for scene_id in to_scenes.keys() - from_scenes.keys():
        scene_changes.append(SceneChange(scene_id=scene_id.value, kind="ADDED"))
    for scene_id in from_scenes.keys() & to_scenes.keys():
        if from_scenes[scene_id] != to_scenes[scene_id]:
            scene_changes.append(SceneChange(scene_id=scene_id.value, kind="MODIFIED"))

    from_orders = {s.scene_id: s.order for s in from_draft.scenes}
    to_orders = {s.scene_id: s.order for s in to_draft.scenes}
    common = from_scenes.keys() & to_scenes.keys()
    for scene_id in common:
        if from_orders[scene_id] != to_orders[scene_id]:
            scene_changes.append(SceneChange(scene_id=scene_id.value, kind="REORDERED"))

    dialogue_changes = _dialogue_changes(from_draft, to_draft)

    summary: Dict[str, int] = {"ADDED": 0, "DELETED": 0, "MODIFIED": 0, "REORDERED": 0}
    for change in scene_changes:
        summary[change.kind] = summary.get(change.kind, 0) + 1
    for change in dialogue_changes:
        summary[change.kind] = summary.get(change.kind, 0) + 1

    return StoryDiff(
        from_draft_id=from_draft.draft_id,
        to_draft_id=to_draft.draft_id,
        scene_changes=scene_changes,
        dialogue_changes=dialogue_changes,
        summary=summary,
    )


def _dialogue_changes(from_draft: ScreenplayDraft, to_draft: ScreenplayDraft) -> list:
    from windagent_core.domain.story.review.models import DialogueChange

    from_lines = {
        line.dialogue_id: (scene.scene_id, line)
        for scene in from_draft.scenes for line in scene.dialogue
    }
    to_lines = {
        line.dialogue_id: (scene.scene_id, line)
        for scene in to_draft.scenes for line in scene.dialogue
    }
    changes: List[DialogueChange] = []
    for dialogue_id in from_lines.keys() - to_lines.keys():
        changes.append(DialogueChange(
            dialogue_id=dialogue_id.value, scene_id=from_lines[dialogue_id][0].value, kind="DELETED",
        ))
    for dialogue_id in to_lines.keys() - from_lines.keys():
        changes.append(DialogueChange(
            dialogue_id=dialogue_id.value, scene_id=to_lines[dialogue_id][0].value, kind="ADDED",
        ))
    for dialogue_id in from_lines.keys() & to_lines.keys():
        if from_lines[dialogue_id] != to_lines[dialogue_id]:
            changes.append(DialogueChange(
                dialogue_id=dialogue_id.value,
                scene_id=to_lines[dialogue_id][0].value,
                kind="MODIFIED",
            ))
    return changes


def validate_story_diff(diff: StoryDiff) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if diff.from_draft_id == diff.to_draft_id:
        issues.append(_issue(
            "DIFF_MISMATCH", json_pointer("from_draft_id"),
            "diff must compare two distinct drafts",
        ))
    expected = {"ADDED": 0, "DELETED": 0, "MODIFIED": 0, "REORDERED": 0}
    for change in [*diff.scene_changes, *diff.dialogue_changes]:
        expected[change.kind] = expected.get(change.kind, 0) + 1
    if diff.summary != expected:
        issues.append(_issue(
            "DIFF_MISMATCH", json_pointer("summary"),
            f"summary {diff.summary} != computed {expected}",
        ))
    return ValidationReport(artifact_type=diff.artifact_type, issues=issues)


def validate_locked_package(
    package: LockedScreenplayPackage,
    receipt: Optional[LockedScreenplayReceipt] = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if receipt is not None and package.receipt_id != receipt.receipt_id:
        issues.append(_issue(
            "REF_MISSING", json_pointer("receipt_id"),
            "package receipt ref does not match the issued receipt",
        ))
    if receipt is not None and receipt.state != READY_FOR_PRODUCTION:
        issues.append(_issue(
            "LOCK_STATE", json_pointer("receipt_id"),
            f"receipt state {receipt.state!r} is not {READY_FOR_PRODUCTION}",
        ))

    seen_ids: List[str] = []
    present_types = set()
    for index, ref in enumerate(package.manifest):
        if not _is_sha256(ref.content_hash):
            issues.append(_issue(
                "MANIFEST_HASH", json_pointer("manifest", index, "content_hash"),
                f"manifest entry {ref.artifact_id} hash is not a 64-char SHA-256",
            ))
        if ref.artifact_id in seen_ids:
            issues.append(_issue(
                "MANIFEST_DUPLICATE", json_pointer("manifest", index, "artifact_id"),
                f"duplicate manifest artifact {ref.artifact_id}",
            ))
        seen_ids.append(ref.artifact_id)
        present_types.add(ref.artifact_type)

    missing = sorted(REQUIRED_PACKAGE_ARTIFACTS - present_types)
    if missing:
        issues.append(_issue(
            "MANIFEST_MISSING_REF", json_pointer("manifest"),
            f"lineage incomplete; missing artifact types: {missing}",
        ))
    return ValidationReport(artifact_type=package.artifact_type, issues=issues)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())
