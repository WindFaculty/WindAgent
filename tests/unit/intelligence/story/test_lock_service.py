"""Plan B B8 unit tests: LockService + LockHandler (S10 lock assembly)."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.verification.produce_b7_evidence import (
    GOLDEN_DRAFT,
    _weak_report,
)

from windagent_core.domain.story.review import (
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewReport,
    validate_locked_package,
)
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_intelligence.story.review import (
    LockService,
    LockValidationFailure,
)
from windagent_intelligence.story.review.service import LockResult
from windagent_intelligence.story.runtime_handlers import LockHandler


def _run(coro):
    return asyncio.run(coro)


def _receipt(
    *,
    approval_mode: str = "AUTO",
    policy_id: str = "",
    draft_id: str | None = None,
    state: str = "READY_FOR_PRODUCTION",
) -> LockedScreenplayReceipt:
    return LockedScreenplayReceipt(
        receipt_id=f"rcpt_{approval_mode.lower()}_{draft_id or GOLDEN_DRAFT.draft_id.value}",
        draft_id=draft_id or GOLDEN_DRAFT.draft_id,
        state=state,
        approval_mode=approval_mode,
        policy_id=policy_id,
    )


def _clean_report() -> ReviewReport:
    return ReviewReport(
        report_id="report_clean_pass",
        draft_id=GOLDEN_DRAFT.draft_id,
        review_iteration=1,
        verdict="PASS",
        quality_summary="0 findings (0 blocking, 0 warnings).",
    )


def _lineage_refs(
    *,
    draft: ScreenplayDraft = GOLDEN_DRAFT,
    report: ReviewReport | None = None,
    receipt: LockedScreenplayReceipt | None = None,
    drop: tuple[str, ...] = (),
    corrupt: tuple[tuple[str, str], ...] = (),
) -> list[PackageArtifactRef]:
    """Full 11-entry lineage (CreativeBrief..Receipt); mutate per test."""
    report = report or _clean_report()
    receipt = receipt or _receipt()
    filler = ["a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64, "f" * 64,
              "1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64]
    refs = [
        PackageArtifactRef(artifact_type=t, artifact_id=f"art_{i}", content_hash=filler[i], revision_id="rev_1")
        for i, t in enumerate([
            "CreativeBrief", "IdeaCandidateSet", "SelectedIdea", "StoryBible",
            "WorldBible", "CharacterCanon", "BeatSheet", "EpisodeOutline",
            "ScreenplayDraft", "ReviewReport", "LockedScreenplayReceipt",
        ])
    ]
    refs = [r for r in refs if r.artifact_type not in drop]
    # Bind the three live artifacts: A-issued ref hash must equal canonical hash.
    for model, artifact_type in (
        (draft, "ScreenplayDraft"),
        (report, "ReviewReport"),
        (receipt, "LockedScreenplayReceipt"),
    ):
        refs = [
            PackageArtifactRef(
                artifact_type=r.artifact_type,
                artifact_id=r.artifact_id,
                content_hash=model.content_hash() if r.artifact_type == artifact_type else r.content_hash,
                revision_id=r.revision_id,
            )
            for r in refs
        ]
    for artifact_type, new_hash in corrupt:
        refs = [
            PackageArtifactRef(
                artifact_type=r.artifact_type,
                artifact_id=r.artifact_id,
                content_hash=new_hash if r.artifact_type == artifact_type else r.content_hash,
                revision_id=r.revision_id,
            )
            for r in refs
        ]
    return refs


# ---------------------------------------------------------------------------
# Happy path: all three approval modes produce a valid immutable package
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "report", "policy_id"),
    [
        ("AUTO", "clean", ""),
        ("HUMAN_REQUIRED", "clean", "approval_policy_v1"),
        ("QUALITY_GATE_ONLY", "weak", ""),
    ],
)
def test_lock_all_approval_modes(mode: str, report: str, policy_id: str) -> None:
    report_obj = _clean_report() if report == "clean" else _weak_report()
    receipt = _receipt(approval_mode=mode, policy_id=policy_id)
    result = LockService().assemble(
        draft=GOLDEN_DRAFT,
        report=report_obj,
        receipt=receipt,
        lineage_refs=_lineage_refs(report=report_obj, receipt=receipt),
    )
    assert isinstance(result, LockResult)
    package = result.package
    assert package.receipt_id == receipt.receipt_id
    assert package.manifest_count == 11
    assert validate_locked_package(package, receipt).is_pass()
    assert result.validation["pass"] is True


def test_lock_package_id_deterministic_and_idempotent():
    receipt = _receipt(approval_mode="AUTO")
    first = LockService().assemble(
        draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
        lineage_refs=_lineage_refs(receipt=receipt),
    )
    second = LockService().assemble(
        draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
        lineage_refs=_lineage_refs(receipt=receipt),
    )
    assert first.package.package_id == second.package.package_id
    assert first.package.content_hash() == second.package.content_hash()
    assert first.package.serialize() == second.package.serialize()


def test_lock_package_is_immutable():
    receipt = _receipt(approval_mode="AUTO")
    result = LockService().assemble(
        draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
        lineage_refs=_lineage_refs(receipt=receipt),
    )
    package = result.package
    assert package.model_config.get("frozen") is True
    assert LockedScreenplayPackage.model_config.get("frozen") is True
    with pytest.raises(Exception):
        package.title = "mutated"  # type: ignore[misc]
    # Manifest refs are frozen too: no entry may be rewritten after assembly.
    ref = package.manifest[0]
    with pytest.raises(Exception):
        ref.content_hash = "0" * 64  # type: ignore[misc]
    # Post-lock mutation attempt via a different draft fails hash binding.
    mutated = ScreenplayDraft(
        **{**json.loads(GOLDEN_DRAFT.serialize()), "title": "Đổi tên sau khi khóa"}
    )
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=mutated,
            report=_clean_report(),
            receipt=_receipt(approval_mode="AUTO"),
            lineage_refs=_lineage_refs(),
        )
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "HASH_MISMATCH" in codes


# ---------------------------------------------------------------------------
# Refusals: missing/stale approval, hash mismatch, policy, lineage
# ---------------------------------------------------------------------------


def test_lock_refuses_wrong_receipt_state():
    receipt = _receipt(approval_mode="AUTO", state="IN_REVIEW")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt),
        )
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "LOCK_STATE" in codes


def test_lock_refuses_stale_receipt_draft():
    receipt = _receipt(approval_mode="AUTO", draft_id="draft_other")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt),
        )
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "RECEIPT_DRAFT_MISMATCH" in codes


def test_lock_refuses_unknown_approval_mode():
    receipt = _receipt(approval_mode="BY_HAND_WAVE")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt),
        )
    assert "APPROVAL_MODE" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_human_required_without_policy():
    receipt = _receipt(approval_mode="HUMAN_REQUIRED", policy_id="")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt),
        )
    assert "APPROVAL_POLICY" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_auto_with_warnings():
    weak = _weak_report()
    receipt = _receipt(approval_mode="AUTO")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=weak, receipt=receipt,
            lineage_refs=_lineage_refs(report=weak, receipt=receipt),
        )
    assert "APPROVAL_MODE" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_non_pass_review():
    blocked = _weak_report()
    blocked = ReviewReport(
        **{**json.loads(blocked.serialize()), "verdict": "REVIEW_REQUIRED"}
    )
    receipt = _receipt(approval_mode="HUMAN_REQUIRED", policy_id="approval_policy_v1")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=blocked, receipt=receipt,
            lineage_refs=_lineage_refs(report=blocked, receipt=receipt),
        )
    assert "REVIEW_THRESHOLD" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_stale_report_draft():
    stale = ReviewReport(
        **{**json.loads(_clean_report().serialize()), "draft_id": "draft_other"}
    )
    receipt = _receipt(approval_mode="AUTO")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=stale, receipt=receipt,
            lineage_refs=_lineage_refs(report=stale, receipt=receipt),
        )
    assert "REVIEW_STALE" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_exhausted_iteration_budget():
    exhausted = _weak_report(review_iteration=4, maximum_iterations=3)
    receipt = _receipt(approval_mode="HUMAN_REQUIRED", policy_id="approval_policy_v1")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=exhausted, receipt=receipt,
            lineage_refs=_lineage_refs(report=exhausted, receipt=receipt),
        )
    assert "REVISION_BUDGET" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_incomplete_lineage():
    receipt = _receipt(approval_mode="AUTO")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt, drop=("WorldBible", "BeatSheet")),
        )
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "MANIFEST_MISSING_REF" in codes


def test_lock_refuses_duplicate_lineage_ref():
    receipt = _receipt(approval_mode="AUTO")
    refs = _lineage_refs(receipt=receipt)
    dup = PackageArtifactRef(
        artifact_type="ScreenplayDraft", artifact_id="art_8",
        content_hash=GOLDEN_DRAFT.content_hash(), revision_id="rev_1",
    )
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=[*refs, dup],
        )
    assert "MANIFEST_DUPLICATE" in {i["code"] for i in exc.value.details["issues"]}


def test_lock_refuses_hash_mismatch_on_report():
    receipt = _receipt(approval_mode="AUTO")
    with pytest.raises(LockValidationFailure) as exc:
        LockService().assemble(
            draft=GOLDEN_DRAFT, report=_clean_report(), receipt=receipt,
            lineage_refs=_lineage_refs(receipt=receipt, corrupt=(("ReviewReport", "a" * 64),)),
        )
    assert "HASH_MISMATCH" in {i["code"] for i in exc.value.details["issues"]}


# ---------------------------------------------------------------------------
# Handler surface
# ---------------------------------------------------------------------------


def test_lock_handler_registered_and_async():
    handler = LockHandler()
    assert handler.task_type.value == "studio.story.lock"
    result = _run(handler.handle(
        GOLDEN_DRAFT,
        _clean_report(),
        _receipt(approval_mode="AUTO"),
        lineage_refs=_lineage_refs(receipt=_receipt(approval_mode="AUTO")),
    ))
    assert result.package.manifest_count == 11
    assert result.package.receipt_id.value.startswith("rcpt_")


def test_lock_handler_rejects_missing_lineage():
    handler = LockHandler()
    with pytest.raises(LockValidationFailure):
        _run(handler.handle(
            GOLDEN_DRAFT,
            _clean_report(),
            _receipt(approval_mode="AUTO"),
            lineage_refs=[],
        ))
