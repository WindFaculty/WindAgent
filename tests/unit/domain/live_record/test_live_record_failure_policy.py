"""Live Record failure policy tests (ban_ke_hoach_v1.md Section 18, Phase F).

Mirrors the frozen ``FAILURE_POLICIES`` table in
frontend/app/src/features/live-record/domain/stateMachine.ts — the gate test
on the TS side asserts exactly three classes exist; here we assert every
canonical failure classifies deterministically and unknown failures
fail-closed to OPERATOR_REQUIRED.
"""

from __future__ import annotations

import pytest

from windagent_core.domain.live_record.failure_policy import (
    FAILURE_CODES,
    FAILURE_POLICIES,
    PROPOSED_TRANSITIONS,
    UNKNOWN_FAILURE_POLICY,
    FailureClass,
    RecoveryAction,
    classify_failure,
    proposed_transition,
)

CLASSES = {FailureClass.RECOVERABLE, FailureClass.OPERATOR_REQUIRED, FailureClass.FATAL}


def test_frozen_table_has_exactly_three_classes():
    assert CLASSES == set(FailureClass)
    used = {policy.failure_class for policy in FAILURE_POLICIES}
    assert used == CLASSES  # every class is reachable from the frozen table


def test_class_determines_recovery_action():
    for policy in FAILURE_POLICIES:
        if policy.failure_class is FailureClass.RECOVERABLE:
            assert policy.action is RecoveryAction.RETRY_RESUME
        elif policy.failure_class is FailureClass.OPERATOR_REQUIRED:
            assert policy.action is RecoveryAction.PAUSE_REQUEST_OPERATOR
        else:
            assert policy.action is RecoveryAction.STOP_FINALIZE


def test_table_size_matches_ts_source_of_truth():
    # 4 RECOVERABLE + 3 OPERATOR_REQUIRED + 5 FATAL = 12 frozen rows.
    assert len(FAILURE_POLICIES) == 12
    assert len(FAILURE_CODES) == len(FAILURE_POLICIES)


@pytest.mark.parametrize(
    ("code", "expected_class"),
    [
        ("GEMINI_DISCONNECT", FailureClass.RECOVERABLE),
        ("BROWSER_PAGE_SLOW", FailureClass.RECOVERABLE),
        ("VISUAL_VERIFY_TIMEOUT", FailureClass.RECOVERABLE),
        ("TOOL_COMMAND_TIMEOUT", FailureClass.RECOVERABLE),
        ("UI_CHANGED", FailureClass.OPERATOR_REQUIRED),
        ("UNEXPECTED_DIALOG", FailureClass.OPERATOR_REQUIRED),
        ("LOGIN_REQUIRED", FailureClass.OPERATOR_REQUIRED),
        ("DISK_FULL", FailureClass.FATAL),
        ("NVENC_FAILURE", FailureClass.FATAL),
        ("CAPTURE_DEVICE_DESTROYED", FailureClass.FATAL),
        ("PLAN_TAMPERED", FailureClass.FATAL),
        ("WORKSPACE_HASH_MISMATCH", FailureClass.FATAL),
    ],
)
def test_canonical_codes_classify(code: str, expected_class: FailureClass):
    policy = classify_failure(code)
    assert policy.failure_class is expected_class


def test_code_lookup_is_case_insensitive_and_tolerates_whitespace():
    assert classify_failure("  disk_full ") is classify_failure("DISK_FULL")


@pytest.mark.parametrize(
    ("description", "expected_action"),
    [
        ("Gemini network disconnect mid-cue", RecoveryAction.RETRY_RESUME),
        ("browser page slow after navigation timeout", RecoveryAction.RETRY_RESUME),
        ("visual verification timeout waiting for green build", RecoveryAction.RETRY_RESUME),
        ("UI changed: selector not found for API Keys", RecoveryAction.PAUSE_REQUEST_OPERATOR),
        ("VS Code unexpected dialog appeared", RecoveryAction.PAUSE_REQUEST_OPERATOR),
        ("website requires login before continuing", RecoveryAction.PAUSE_REQUEST_OPERATOR),
        ("disk full while writing segment_0007.mkv", RecoveryAction.STOP_FINALIZE),
        ("NVENC failure: encoder returned -10", RecoveryAction.STOP_FINALIZE),
        ("capture device destroyed by ddagrab", RecoveryAction.STOP_FINALIZE),
        ("plan tampered: plan_hash mismatch", RecoveryAction.STOP_FINALIZE),
    ],
)
def test_free_text_descriptions_classify(description: str, expected_action: RecoveryAction):
    assert classify_failure(description).action is expected_action


@pytest.mark.parametrize("unknown", ["", "   ", "totally novel catastrophe", "quantum flake"])
def test_unknown_failures_fail_closed_to_operator_required(unknown: str):
    policy = classify_failure(unknown)
    assert policy is UNKNOWN_FAILURE_POLICY or policy == UNKNOWN_FAILURE_POLICY
    assert policy.failure_class is FailureClass.OPERATOR_REQUIRED
    assert policy.action is RecoveryAction.PAUSE_REQUEST_OPERATOR


def test_proposed_transitions_cover_every_recovery_action():
    assert set(PROPOSED_TRANSITIONS) == set(RecoveryAction)
    for action, description in PROPOSED_TRANSITIONS.items():
        assert description  # non-empty contract text

    # Spot-check the semantic anchors of each transition family.
    assert "sessionResumption" in proposed_transition(classify_failure("GEMINI_DISCONNECT"))
    assert "PAUSED" in proposed_transition(classify_failure("UI_CHANGED"))
    assert "FAILED" in proposed_transition(classify_failure("DISK_FULL"))


def test_no_failure_is_both_recoverable_and_fatal():
    """Guard against a future edit silently widening a FATAL row."""
    fatal_descriptions = {
        policy.failure for policy in FAILURE_POLICIES if policy.failure_class is FailureClass.FATAL
    }
    recoverable_descriptions = {
        policy.failure for policy in FAILURE_POLICIES if policy.failure_class is FailureClass.RECOVERABLE
    }
    assert not fatal_descriptions & recoverable_descriptions
