"""B1 review/lock: aggregation, diff, proposals, package lineage."""

from __future__ import annotations

from windagent_core.domain.story.ids import (
    LockedScreenplayPackageId,
    LockedScreenplayReceiptId,
    ReviewReportId,
    RevisionProposalId,
    ScreenplayDraftId,
)
from windagent_core.domain.story.review import (
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewFinding,
    ReviewReport,
    RevisionProposal,
    aggregate_findings,
    build_story_diff,
    validate_locked_package,
    validate_review_report,
    validate_revision_proposal,
    validate_story_diff,
)
from windagent_core.domain.story.validation import ValidationSeverity

DRAFT_A = ScreenplayDraftId("draft_a")
DRAFT_B = ScreenplayDraftId("draft_b")


def _finding(code: str, location: str = "/scenes/0", severity: ValidationSeverity = ValidationSeverity.WARNING) -> ReviewFinding:
    return ReviewFinding(code=code, severity=severity, location=location, evidence="e", source="deterministic")


def test_aggregation_dedups_and_orders():
    findings = aggregate_findings([
        _finding("B", location="/z"),
        _finding("A", location="/scenes/0", severity=ValidationSeverity.BLOCKING),
        _finding("A", location="/scenes/0", severity=ValidationSeverity.BLOCKING),  # duplicate
        _finding("C", location="/a", severity=ValidationSeverity.INFO),
    ])
    assert len(findings) == 3
    assert findings[0].code == "A"  # BLOCKING first
    assert [f.code for f in findings] == ["A", "B", "C"]


def test_review_verdict_consistency():
    report = ReviewReport(
        report_id=ReviewReportId.generate("rr"),
        draft_id=DRAFT_A,
        verdict="PASS",
        findings=[_finding("FORMAT_VALIDITY", severity=ValidationSeverity.BLOCKING)],
    )
    validation = validate_review_report(report)
    assert any(i.code == "REVIEW_VERDICT" for i in validation.issues)
    assert report.is_pass is False


def test_revision_proposal_binds_to_report():
    report = ReviewReport(
        report_id=ReviewReportId("rr_1"),
        draft_id=DRAFT_A,
        verdict="REVIEW_REQUIRED",
        findings=[_finding("FORMAT_VALIDITY"), _finding("DURATION_SUM")],
    )
    proposal = RevisionProposal(
        proposal_id=RevisionProposalId.generate("prop"),
        draft_id=DRAFT_A,
        review_report_id=report.report_id,
        accepted_finding_codes=["FORMAT_VALIDITY", "DURATION_SUM"],
        revision_reason="Sửa lỗi định dạng và thời lượng.",
        iteration_number=1,
    )
    assert validate_revision_proposal(proposal, report).is_pass()


def test_revision_proposal_stale_findings_blocked():
    report = ReviewReport(
        report_id=ReviewReportId("rr_2"), draft_id=DRAFT_A,
        verdict="REVIEW_REQUIRED", findings=[_finding("FORMAT_VALIDITY")],
    )
    proposal = RevisionProposal(
        proposal_id=RevisionProposalId.generate("prop"),
        draft_id=DRAFT_A,
        review_report_id=report.report_id,
        accepted_finding_codes=["FORMAT_VALIDITY", "GHOST_CODE"],
        revision_reason="r",
    )
    validation = validate_revision_proposal(proposal, report)
    assert any(i.code == "REVISION_STALE" for i in validation.issues)


def test_revision_budget_exhaustion():
    proposal = RevisionProposal(
        proposal_id=RevisionProposalId.generate("prop"),
        draft_id=DRAFT_A,
        review_report_id=ReviewReportId("rr_3"),
        accepted_finding_codes=[],
        revision_reason="r",
        iteration_number=3,
        maximum_iterations=3,
    )
    assert proposal.budget_exhausted


def test_story_diff_correctness_and_immutability():
    from windagent_core.domain.story.screenplay import DraftDialogueLine, DraftScene, ScreenplayDraft
    from windagent_core.domain.story.ids import (
        DialogueLineId,
        DraftSceneId,
        OutlineSceneId,
        StoryCharacterId,
        StoryLocationId,
    )

    def draft(draft_id: ScreenplayDraftId, extra_line: bool) -> ScreenplayDraft:
        scene = DraftScene(
            scene_id=DraftSceneId("s1"), order=1, outline_scene_id=OutlineSceneId("o1"),
            location_id=StoryLocationId("loc"), character_ids=[StoryCharacterId("ch")],
            action_description="A", estimated_seconds=30,
        )
        if extra_line:
            scene = scene.model_copy(update={
                "dialogue": [DraftDialogueLine(
                    dialogue_id=DialogueLineId("dl"), scene_id=scene.scene_id,
                    character_id=StoryCharacterId("ch"), order=1, text="Xin chào!",
                )]
            })
        return ScreenplayDraft(draft_id=draft_id, title="T", target_duration_seconds=240, scenes=[scene])

    before = draft(DRAFT_A, extra_line=False)
    after = draft(DRAFT_B, extra_line=True)
    diff = build_story_diff(before, after)
    assert diff.from_draft_id == DRAFT_A and diff.to_draft_id == DRAFT_B
    assert any(c.kind == "MODIFIED" for c in diff.scene_changes)
    assert any(c.kind == "ADDED" for c in diff.dialogue_changes)
    assert validate_story_diff(diff).is_pass()
    # Inputs untouched.
    assert before.scenes[0].dialogue == []


def test_locked_package_lineage_and_manifest():
    receipt = LockedScreenplayReceipt(
        receipt_id=LockedScreenplayReceiptId.generate("rcpt"),
        draft_id=DRAFT_A,
        approval_mode="AUTO",
    )
    package = LockedScreenplayPackage(
        package_id=LockedScreenplayPackageId.generate("pkg"),
        receipt_id=receipt.receipt_id,
        title="Con thỏ và cánh diều",
        manifest=[
            PackageArtifactRef(artifact_type=t, artifact_id=f"art_{i}", content_hash="a" * 64, revision_id="rev_1")
            for i, t in enumerate([
                "ScreenplayDraft", "ReviewReport", "LockedScreenplayReceipt",
                "SelectedIdea", "StoryBible", "WorldBible", "CharacterCanon",
                "BeatSheet", "EpisodeOutline",
            ])
        ],
    )
    validation = validate_locked_package(package, receipt)
    assert validation.is_pass(), validation.summary()
    assert package.to_summary()["manifest_count"] == 9


def test_locked_package_missing_lineage_blocks():
    receipt = LockedScreenplayReceipt(
        receipt_id=LockedScreenplayReceiptId.generate("rcpt"), draft_id=DRAFT_A,
    )
    package = LockedScreenplayPackage(
        package_id=LockedScreenplayPackageId.generate("pkg"),
        receipt_id=receipt.receipt_id,
        title="T",
        manifest=[PackageArtifactRef(artifact_type="ScreenplayDraft", artifact_id="a1", content_hash="b" * 64)],
    )
    validation = validate_locked_package(package, receipt)
    assert any(i.code == "MANIFEST_MISSING_REF" for i in validation.issues)


def test_manifest_hash_and_duplicate_checks():
    receipt = LockedScreenplayReceipt(
        receipt_id=LockedScreenplayReceiptId.generate("rcpt"), draft_id=DRAFT_A,
    )
    package = LockedScreenplayPackage(
        package_id=LockedScreenplayPackageId.generate("pkg"),
        receipt_id=receipt.receipt_id,
        title="T",
        manifest=[
            PackageArtifactRef(artifact_type="ScreenplayDraft", artifact_id="a1", content_hash="z" * 64),
            PackageArtifactRef(artifact_type="ScreenplayDraft", artifact_id="a1", content_hash="c" * 64),
        ],
    )
    validation = validate_locked_package(package, receipt)
    codes = {i.code for i in validation.issues}
    assert "MANIFEST_HASH" in codes and "MANIFEST_DUPLICATE" in codes


def test_receipt_state_must_be_ready():
    receipt = LockedScreenplayReceipt(
        receipt_id=LockedScreenplayReceiptId.generate("rcpt"), draft_id=DRAFT_A,
        state="DRAFT",
    )
    package = LockedScreenplayPackage(
        package_id=LockedScreenplayPackageId.generate("pkg"),
        receipt_id=receipt.receipt_id,
        title="T",
        manifest=[PackageArtifactRef(artifact_type="ScreenplayDraft", artifact_id="a1", content_hash="d" * 64)],
    )
    validation = validate_locked_package(package, receipt)
    assert any(i.code == "LOCK_STATE" for i in validation.issues)
