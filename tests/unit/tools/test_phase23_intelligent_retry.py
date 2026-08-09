"""VP3D Phase 23 - intelligent retry acceptance tests.

Covers Stage K §4 components (FailureClassifier, RepairPlanner,
InvalidationPlanner, RetryBudgetPolicy, RepairExecutionReceipt +
IntelligentRetryCoordinator) against the Stage K §5 matrix: finding ->
owner/smallest repair unit mapping, uncertainty kept below the confidence
threshold (no auto-pick), dependency-scoped invalidation (unrelated approved
shots untouched), failure-signature dedupe (duplicate event/restart runs a
repair once), retry-loop + budget exhaustion escalation, and rerun of the
FULL related + downstream check set after a repair.
"""

from __future__ import annotations


from windagent_tools.production_engines.blender import (
    DOWNSTREAM_CHECKS,
    OWNER_AMBIGUOUS,
    OWNER_ASSET,
    OWNER_CAMERA,
    OWNER_FACIAL,
    OWNER_POST_PRODUCTION,
    OWNER_RENDER,
    REPAIR_UNIT_AFFECTED_FRAMES,
    REPAIR_UNIT_ASSET_REVISION,
    REPAIR_UNIT_AUDIO_MIX,
    REPAIR_UNIT_CAMERA_RECOMPILE,
    REPAIR_UNIT_FACIAL_TRACK,
    REPAIR_UNIT_HUMAN_REVIEW,
    STATUS_BLOCKED,
    STATUS_ESCALATED,
    STATUS_FAILED,
    STATUS_SKIPPED_DUPLICATE,
    STATUS_SUCCEEDED,
    FailureClassifier,
    IntelligentRetryCoordinator,
    InvalidationPlanner,
    RepairPlanner,
    RetryBudgetPolicy,
    failure_signature,
)


def _finding(
    code,
    entity="render",
    suggested_repair="human_review",
    confidence=1.0,
    frame_range=None,
    causes=(),
):
    return {
        "code": code,
        "entity": entity,
        "frame_range": frame_range,
        "evidence": {},
        "confidence": confidence,
        "suggested_repair": suggested_repair,
        "causes": list(causes),
    }


def _graph() -> dict:
    return {
        "shot_01_render": ["camera", "facial_track", "render"],
        "shot_02_render": ["camera", "render"],
        "shot_03_render": ["asset", "render"],
        "shot_04_render": ["render"],
    }


# ---------------------------------------------------------------------------
# FailureClassifier (backlog item 1): finding -> owner + smallest unit
# ---------------------------------------------------------------------------
def test_missing_texture_maps_to_asset_repair():
    classification = FailureClassifier().classify(
        _finding("MISSING_TEXTURE", entity="tex_table", suggested_repair="asset_revision")
    )
    assert classification.owner == OWNER_ASSET
    assert classification.repair_unit == REPAIR_UNIT_ASSET_REVISION
    assert classification.revised_input_key == "asset"
    assert not classification.ambiguous


def test_camera_collision_maps_to_camera_recompile():
    classification = FailureClassifier().classify(
        _finding(
            "CAMERA_CHARACTER_COLLISION",
            entity="char_hero",
            suggested_repair="camera_recompile",
        )
    )
    assert classification.owner == OWNER_CAMERA
    assert classification.repair_unit == REPAIR_UNIT_CAMERA_RECOMPILE
    assert classification.revised_input_key == "camera"


def test_lip_sync_maps_to_facial_only():
    classification = FailureClassifier().classify(
        _finding(
            "LIP_SYNC_MISMATCH",
            entity="facial",
            suggested_repair="facial_only",
            causes=("audio_alignment", "facial_animation"),
        )
    )
    assert classification.owner == OWNER_FACIAL
    assert classification.repair_unit == REPAIR_UNIT_FACIAL_TRACK
    assert classification.revised_input_key == "facial_track"


def test_noise_maps_to_affected_frames():
    classification = FailureClassifier().classify(
        _finding("NOISE_BURST", suggested_repair="affected_frames")
    )
    assert classification.owner == OWNER_RENDER
    assert classification.repair_unit == REPAIR_UNIT_AFFECTED_FRAMES
    assert classification.revised_input_key == "render"


def test_audio_timing_maps_to_audio_mix():
    classification = FailureClassifier().classify(
        _finding("AUDIO_TIMING", suggested_repair="audio_mix")
    )
    assert classification.owner == OWNER_POST_PRODUCTION
    assert classification.repair_unit == REPAIR_UNIT_AUDIO_MIX


def test_low_confidence_keeps_uncertainty_no_auto_pick():
    # §5: one defect, many possible causes, confidence below threshold ->
    # keep uncertainty, never self-select a repair.
    classification = FailureClassifier().classify(
        _finding(
            "LIP_SYNC_MISMATCH",
            suggested_repair="facial_only",
            confidence=0.4,
            causes=("audio_alignment", "facial_animation"),
        )
    )
    assert classification.ambiguous is True
    assert classification.owner == OWNER_AMBIGUOUS
    assert classification.repair_unit == REPAIR_UNIT_HUMAN_REVIEW
    assert classification.causes == ("audio_alignment", "facial_animation")


def test_human_review_scope_is_always_ambiguous():
    classification = FailureClassifier().classify(
        _finding("CROSS_SHOT_IDENTITY_MISMATCH", suggested_repair="human_review")
    )
    assert classification.ambiguous is True
    assert classification.owner == OWNER_AMBIGUOUS


def test_high_confidence_multi_cause_still_picks_smallest_unit():
    # Multiple candidate causes with HIGH confidence -> smallest unit kept
    # (facial-only), causes preserved for the repair receipt.
    classification = FailureClassifier().classify(
        _finding(
            "LIP_SYNC_MISMATCH",
            suggested_repair="facial_only",
            confidence=0.95,
            causes=("audio_alignment", "facial_animation"),
        )
    )
    assert classification.ambiguous is False
    assert classification.repair_unit == REPAIR_UNIT_FACIAL_TRACK
    assert classification.causes == ("audio_alignment", "facial_animation")


# ---------------------------------------------------------------------------
# RepairPlanner (backlog items 2-3): smallest unit + full rerun set + lock
# ---------------------------------------------------------------------------
def test_plan_reruns_related_and_downstream_checks_not_just_failure():
    classification = FailureClassifier().classify(
        _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only")
    )
    plan = RepairPlanner().plan(
        classification, finding=_finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only")
    )
    rerun = set(plan.rerun_checks)
    assert "LIP_SYNC_MISMATCH" in rerun  # the failed check
    assert "IDENTITY_DRIFT" in rerun  # related facial check
    assert "FRAME_COUNT_MISMATCH" in rerun  # downstream
    assert "NOISE_BURST" in rerun  # downstream
    assert set(DOWNSTREAM_CHECKS) <= rerun


def test_plan_blocks_on_locked_artifact():
    classification = FailureClassifier().classify(
        _finding("MISSING_TEXTURE", entity="tex_a", suggested_repair="asset_revision")
    )
    plan = RepairPlanner().plan(
        classification,
        finding=_finding("MISSING_TEXTURE", entity="tex_a", suggested_repair="asset_revision"),
        locked_artifacts=["shot_03_render"],
    )
    assert plan.blocked is True
    assert "locked" in plan.block_reason


def test_plan_blocks_on_ambiguous_owner():
    classification = FailureClassifier().classify(
        _finding("VLM_REVIEW_TIMEOUT", suggested_repair="human_review", confidence=0.0)
    )
    plan = RepairPlanner().plan(
        classification, finding=_finding("VLM_REVIEW_TIMEOUT", confidence=0.0)
    )
    assert plan.blocked is True
    assert "human review" in plan.block_reason


# ---------------------------------------------------------------------------
# InvalidationPlanner (backlog item 3 + §5): dependency-scoped, no collateral
# ---------------------------------------------------------------------------
def test_invalidation_only_touches_dependent_artifacts():
    receipt = InvalidationPlanner().invalidate(
        revised_inputs={"facial_track": "facial:rev2"},
        dependency_graph=_graph(),
    )
    assert "shot_01_render" in receipt.invalidated_artifacts  # depends on facial
    assert "shot_02_render" not in receipt.invalidated_artifacts  # no facial dep
    assert "shot_03_render" not in receipt.invalidated_artifacts
    assert "shot_04_render" not in receipt.invalidated_artifacts
    assert "shot_02_render" in receipt.preserved_artifacts  # approved shot kept


def test_camera_repair_invalidates_only_camera_dependent_shots():
    receipt = InvalidationPlanner().invalidate(
        revised_inputs={"camera": "cam:rev2"},
        dependency_graph=_graph(),
    )
    assert set(receipt.invalidated_artifacts) == {"shot_01_render", "shot_02_render"}
    assert "shot_03_render" in receipt.preserved_artifacts
    assert "shot_04_render" in receipt.preserved_artifacts


def test_empty_revised_inputs_invalidate_nothing():
    receipt = InvalidationPlanner().invalidate(
        revised_inputs={}, dependency_graph=_graph()
    )
    assert receipt.invalidated_artifacts == ()
    assert len(receipt.preserved_artifacts) == 4


# ---------------------------------------------------------------------------
# RetryBudgetPolicy (backlog item 4): dedupe + budgets + loop detection
# ---------------------------------------------------------------------------
def test_same_signature_repeated_reaches_loop_detection():
    budget = RetryBudgetPolicy(max_attempts=2, max_cost=10.0)
    signature = failure_signature(
        _finding("NOISE_BURST", suggested_repair="affected_frames")
    )
    assert budget.allow(signature).allowed is True
    budget.register(signature, cost=1.0)
    assert budget.allow(signature).allowed is True
    budget.register(signature, cost=1.0)
    decision = budget.allow(signature)
    assert decision.allowed is False
    assert "repair loop detected" in decision.reason
    assert decision.attempts == 2


def test_cost_budget_exhaustion_blocks():
    budget = RetryBudgetPolicy(max_attempts=5, max_cost=5.0)
    signature = failure_signature(
        _finding("NOISE_BURST", suggested_repair="affected_frames")
    )
    budget.register(signature, cost=4.0)
    decision = budget.allow(signature, cost=2.0)
    assert decision.allowed is False
    assert "cost budget exhausted" in decision.reason


def test_different_signatures_have_independent_budgets():
    budget = RetryBudgetPolicy(max_attempts=1, max_cost=1.0)
    sig_a = failure_signature(_finding("NOISE_BURST", suggested_repair="affected_frames"))
    sig_b = failure_signature(_finding("NOISE_BURST", entity="render2", suggested_repair="affected_frames"))
    budget.register(sig_a, cost=1.0)
    assert budget.allow(sig_a).allowed is False  # exhausted
    assert budget.allow(sig_b).allowed is True  # unrelated signature fresh


# ---------------------------------------------------------------------------
# Coordinator (backlog items 4-6): dedupe, escalation, full rerun
# ---------------------------------------------------------------------------
def test_successful_repair_succeeds_with_full_rerun():
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only"),
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_SUCCEEDED
    assert receipt.classification.repair_unit == REPAIR_UNIT_FACIAL_TRACK
    assert set(receipt.rerun_results) == set(receipt.plan.rerun_checks)
    assert "shot_01_render" in receipt.invalidation.invalidated_artifacts
    assert "shot_02_render" in receipt.invalidation.preserved_artifacts


def test_duplicate_in_flight_event_is_skipped():
    # §5: duplicate event/restart never runs the same repair twice. A
    # re-entrant duplicate dispatch for the SAME signature is SKIPPED while
    # the first repair is still in flight.
    coordinator = IntelligentRetryCoordinator()
    duplicate_receipts = []

    def reentrant_executor(plan):
        duplicate_receipts.append(
            coordinator.execute(
                _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only"),
                dependency_graph=_graph(),
                repair_executor=lambda p: True,
                check_runner=lambda c: {x: True for x in c},
            )
        )
        return True

    receipt = coordinator.execute(
        _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only"),
        dependency_graph=_graph(),
        repair_executor=reentrant_executor,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_SUCCEEDED
    assert len(duplicate_receipts) == 1
    assert duplicate_receipts[0].status == STATUS_SKIPPED_DUPLICATE
    assert "in flight" in duplicate_receipts[0].reason


def test_replay_of_succeeded_signature_is_skipped():
    # Restart after a successful repair re-delivers the same event; the
    # repaired signature must NOT run again.
    coordinator = IntelligentRetryCoordinator()
    finding = _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only")
    first = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert first.status == STATUS_SUCCEEDED
    replay = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,  # would fail if it ran
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert replay.status == STATUS_SKIPPED_DUPLICATE
    assert "already repaired" in replay.reason


def test_failed_signature_is_not_skipped_by_dedupe():
    # Dedupe only guards in-flight + succeeded; a FAILED repair is retried
    # (bounded by the budget) instead of being silently dropped.
    coordinator = IntelligentRetryCoordinator()
    finding = _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only")
    first = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert first.status == STATUS_FAILED
    second = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert second.status == STATUS_SUCCEEDED


def test_repair_that_does_not_fix_is_failed():
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding("MISSING_TEXTURE", entity="tex_a", suggested_repair="asset_revision"),
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_FAILED
    assert "did not fix" in receipt.reason


def test_rerun_failure_marks_failed():
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding("NOISE_BURST", suggested_repair="affected_frames"),
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: c != "NOISE_BURST" for c in checks},
    )
    assert receipt.status == STATUS_FAILED
    assert receipt.rerun_results["NOISE_BURST"] is False


def test_duplicate_event_runs_repair_once_then_escalates_on_loop():
    coordinator = IntelligentRetryCoordinator(
        budget=RetryBudgetPolicy(max_attempts=2, max_cost=10.0)
    )
    finding = _finding("NOISE_BURST", suggested_repair="affected_frames")
    first = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,  # still broken
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert first.status == STATUS_FAILED
    second = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,
        check_runner=lambda checks: {c: True for c in checks},
    )
    # Same signature repeated: budget blocks the third attempt instead of
    # looping forever (repair loop -> escalation, Stage K §5).
    assert second.status == STATUS_FAILED
    third = coordinator.execute(
        finding,
        dependency_graph=_graph(),
        repair_executor=lambda plan: False,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert third.status == STATUS_ESCALATED
    assert "loop" in third.reason


def test_low_confidence_finding_escalates_no_repair_run():
    calls = []
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding(
            "LIP_SYNC_MISMATCH",
            suggested_repair="facial_only",
            confidence=0.2,
            causes=("a", "b"),
        ),
        dependency_graph=_graph(),
        repair_executor=lambda plan: calls.append(1) or True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_ESCALATED
    assert calls == []  # no repair executed
    assert receipt.classification.ambiguous is True


def test_locked_artifact_blocks_before_execution():
    calls = []
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding("MISSING_TEXTURE", entity="tex_a", suggested_repair="asset_revision"),
        dependency_graph=_graph(),
        locked_artifacts=["shot_03_render"],
        repair_executor=lambda plan: calls.append(1) or True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_BLOCKED
    assert calls == []


def test_vlm_timeout_never_becomes_pass():
    # Stage K §5: reviewer/VLM timeout must not become PASS. Phase 22 emits
    # a 0.0-confidence VLM_REVIEW_TIMEOUT finding; the retry layer escalates.
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding(
            "VLM_REVIEW_TIMEOUT",
            suggested_repair="human_review",
            confidence=0.0,
        ),
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    assert receipt.status == STATUS_ESCALATED
    assert receipt.classification.owner == OWNER_AMBIGUOUS


def test_signature_ignores_evidence_but_pins_code_entity_range():
    a = failure_signature(_finding("NOISE_BURST", frame_range=[1, 10], suggested_repair="affected_frames"))
    b = failure_signature(_finding("NOISE_BURST", frame_range=[1, 10], suggested_repair="affected_frames"))
    c = failure_signature(_finding("NOISE_BURST", frame_range=[1, 20], suggested_repair="affected_frames"))
    assert a == b  # same defect, same signature
    assert a != c  # different frame range = different defect


def test_receipt_dict_round_trip():
    coordinator = IntelligentRetryCoordinator()
    receipt = coordinator.execute(
        _finding("LIP_SYNC_MISMATCH", suggested_repair="facial_only"),
        dependency_graph=_graph(),
        repair_executor=lambda plan: True,
        check_runner=lambda checks: {c: True for c in checks},
    )
    data = receipt.to_dict()
    assert data["status"] == STATUS_SUCCEEDED
    assert data["plan"]["rerun_checks"]
    assert "shot_02_render" in data["invalidation"]["preserved_artifacts"]
