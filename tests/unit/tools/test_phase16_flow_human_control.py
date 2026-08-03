"""
Unit tests for Phase 16: Human Intervention and Account Safety (`windagent_tools.google_flow.human_control`).
"""

import pytest
from windagent_tools.google_flow import (
    FlowAccountSafetyPolicy,
    FlowCircuitBreakerTrippedError,
    FlowConcurrencyLimitExceededError,
    FlowHumanActionBlockedError,
    FlowHumanActionRecord,
    FlowHumanActionStatus,
    FlowHumanBypassAttemptedError,
    FlowHumanControlDetector,
    FlowHumanControlError,
    FlowHumanControlManager,
    FlowHumanState,
    FlowJobRecord,
    FlowJobRegistry,
    FlowJobStatus,
    FlowRateLimitExceededError,
    FlowUiObservation,
    FlowUiState,
)


def test_detector_identifies_all_five_human_states():
    # 1. Login
    obs_login = FlowUiObservation(url="https://accounts.google.com/signin", markers=("Choose an account",))
    assert FlowHumanControlDetector.detect(obs_login) == FlowHumanState.HUMAN_LOGIN_REQUIRED

    # 2. CAPTCHA
    obs_captcha = FlowUiObservation(url="https://flow.google.com", markers=("recaptcha challenge", "verify human"))
    assert FlowHumanControlDetector.detect(obs_captcha) == FlowHumanState.HUMAN_CAPTCHA_REQUIRED

    # 3. Account Verification
    obs_verif = FlowUiObservation(url="https://flow.google.com", markers=("2-step verification", "enter code"))
    assert FlowHumanControlDetector.detect(obs_verif) == FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED

    # 4. Payment
    obs_pay = FlowUiObservation(url="https://flow.google.com/billing", markers=("buy credits", "add payment method"))
    assert FlowHumanControlDetector.detect(obs_pay) == FlowHumanState.HUMAN_PAYMENT_CONFIRMATION_REQUIRED

    # 5. Terms
    obs_terms = FlowUiObservation(url="https://flow.google.com/terms", markers=("accept terms of service",))
    assert FlowHumanControlDetector.detect(obs_terms) == FlowHumanState.HUMAN_TERMS_ACCEPTANCE_REQUIRED


def test_detector_unknown_challenge_fail_closed():
    obs_unknown = FlowUiObservation(url="https://accounts.google.com/unknown_security_check", markers=("security check",))
    detected = FlowHumanControlDetector.detect(obs_unknown, expected_state=FlowUiState.SUBMIT_READY)
    assert detected == FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED or detected == FlowHumanState.HUMAN_LOGIN_REQUIRED


def test_zero_bypass_rule_enforcement():
    policy = FlowAccountSafetyPolicy()
    with pytest.raises(FlowHumanBypassAttemptedError):
        policy.assert_no_automated_bypass("solve_captcha_with_ocr")

    with pytest.raises(FlowHumanBypassAttemptedError):
        policy.assert_no_automated_bypass("auto_buy_credits")

    # Safe action should pass
    policy.assert_no_automated_bypass("click_create_project")


def test_evidence_redaction():
    raw_evidence = {
        "user_email": "operator@example.com",
        "session_token": "secret_token_12345",
        "cookie_header": "sessionid=abcde12345",
        "card": "4111-2222-3333-4444",
        "safe_marker": "editor_ready",
    }
    redacted = FlowAccountSafetyPolicy.redact_dict(raw_evidence)
    assert redacted["user_email"] == "[REDACTED]"
    assert redacted["session_token"] == "[REDACTED_SECRET]"
    assert redacted["cookie_header"] == "[REDACTED_SECRET]"
    assert redacted["card"] == "[REDACTED]"
    assert redacted["safe_marker"] == "editor_ready"


def test_circuit_breaker_trips():
    policy = FlowAccountSafetyPolicy(max_interventions_per_session=2)
    policy.record_intervention("sess_1")
    policy.record_intervention("sess_1")
    with pytest.raises(FlowCircuitBreakerTrippedError):
        policy.record_intervention("sess_1")


def test_pause_session_and_block_actions():
    manager = FlowHumanControlManager()
    record = manager.create_human_action(
        session_id="sess_100",
        project_id="proj_1",
        human_state=FlowHumanState.HUMAN_CAPTCHA_REQUIRED,
        reason="CAPTCHA challenge",
        safe_resume_state=FlowUiState.PROJECT_OPEN,
        raw_evidence={"cookie": "secret_abc"},
    )
    assert record.status == FlowHumanActionStatus.PENDING

    with pytest.raises(FlowHumanActionBlockedError):
        manager.assert_session_active("sess_100")

    instructions = manager.get_takeover_instructions(record.human_action_id)
    assert instructions["human_state"] == FlowHumanState.HUMAN_CAPTCHA_REQUIRED.value
    assert "user_action_required" in instructions


def test_human_action_persists_and_restores_the_paused_session(tmp_path):
    manager = FlowHumanControlManager(state_dir=str(tmp_path))
    record = manager.create_human_action(
        session_id="sess_durable",
        project_id="proj_1",
        human_state=FlowHumanState.HUMAN_CAPTCHA_REQUIRED,
        reason="challenge contains operator@example.com",
        safe_resume_state=FlowUiState.GENERATING,
        raw_evidence={"session_token": "never-store-this"},
        generation_id="gen_durable",
    )

    # A new process sees the same pending takeover and therefore remains
    # fail-closed until the documented resume protocol completes.
    reloaded = FlowHumanControlManager(state_dir=str(tmp_path))
    restored = reloaded.get_record(record.human_action_id)
    assert restored is not None
    assert restored.status == FlowHumanActionStatus.PENDING
    assert restored.redacted_evidence["session_token"] == "[REDACTED_SECRET]"
    with pytest.raises(FlowHumanActionBlockedError):
        reloaded.assert_session_active("sess_durable")

    audit = reloaded.execute_safe_resume(
        human_action_id=record.human_action_id,
        resolved_by="operator_1",
        current_observation=FlowUiObservation(
            url="https://flow.google.com/projects/fp_1",
            markers=("project open", "create workspace"),
        ),
        expected_project_id="proj_1",
        project_verifier=lambda project_id, _: project_id == "proj_1",
    )
    assert audit["project_verified"] is True

    recovered_after_resume = FlowHumanControlManager(state_dir=str(tmp_path))
    assert (
        recovered_after_resume.get_record(record.human_action_id).status
        == FlowHumanActionStatus.RESOLVED
    )
    recovered_after_resume.assert_session_active("sess_durable")


def test_account_safety_enforces_concurrency_and_rate_limits():
    now = [1_000.0]
    concurrency_policy = FlowAccountSafetyPolicy(
        max_concurrency=1, rate_limit_per_minute=10, clock=lambda: now[0]
    )
    manager = FlowHumanControlManager(safety_policy=concurrency_policy)
    manager.begin_automated_action("sess_1", "operation_1")
    with pytest.raises(FlowConcurrencyLimitExceededError):
        manager.begin_automated_action("sess_2", "operation_2")
    manager.end_automated_action("sess_1", "operation_1")

    rate_policy = FlowAccountSafetyPolicy(
        max_concurrency=1, rate_limit_per_minute=1, clock=lambda: now[0]
    )
    rate_limited_manager = FlowHumanControlManager(safety_policy=rate_policy)
    rate_limited_manager.begin_automated_action("sess_rate", "operation_1")
    rate_limited_manager.end_automated_action("sess_rate", "operation_1")
    with pytest.raises(FlowRateLimitExceededError):
        rate_limited_manager.begin_automated_action("sess_rate", "operation_2")
    now[0] += 60.0
    rate_limited_manager.begin_automated_action("sess_rate", "operation_3")


def test_safe_resume_protocol_success(tmp_path):
    manager = FlowHumanControlManager()
    registry = FlowJobRegistry(state_dir=str(tmp_path))
    registry.create_prepared(
        generation_id="gen_555",
        project_id="proj_1",
        revision_id="rev_1",
        shot_id="shot_1",
        provider="google_flow_browser",
        request_hash="a" * 64,
        browser_session_id="sess_200",
        flow_project_id="flow_p1",
    )
    registry.mark("gen_555", FlowJobStatus.SUBMITTING)

    record = manager.create_human_action(
        session_id="sess_200",
        project_id="proj_1",
        human_state=FlowHumanState.HUMAN_CAPTCHA_REQUIRED,
        reason="CAPTCHA challenge",
        safe_resume_state=FlowUiState.PROJECT_OPEN,
        raw_evidence={"url": "https://flow.google.com/p1"},
        generation_id="gen_555",
    )

    clean_obs = FlowUiObservation(url="https://flow.google.com/p1", markers=("project open", "create workspace"))
    audit = manager.execute_safe_resume(
        human_action_id=record.human_action_id,
        resolved_by="human_operator_1",
        current_observation=clean_obs,
        expected_project_id="proj_1",
        job_registry=registry,
    )

    reconciled_job = registry.get("gen_555")
    assert audit["duplicate_submit_prevented"] is True
    assert audit["reconciled_job_status"] == FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION.value
    assert reconciled_job.status == FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION
    assert record.status == FlowHumanActionStatus.RESOLVED

    # Session should no longer be paused
    manager.assert_session_active("sess_200")


def test_safe_resume_fails_if_challenge_remains():
    manager = FlowHumanControlManager()
    record = manager.create_human_action(
        session_id="sess_300",
        project_id="proj_1",
        human_state=FlowHumanState.HUMAN_LOGIN_REQUIRED,
        reason="Login required",
        safe_resume_state=FlowUiState.READY,
        raw_evidence={},
    )

    dirty_obs = FlowUiObservation(url="https://accounts.google.com/signin", markers=("sign in",))
    with pytest.raises(FlowHumanControlError) as exc_info:
        manager.execute_safe_resume(
            human_action_id=record.human_action_id,
            resolved_by="human_operator_1",
            current_observation=dirty_obs,
            expected_project_id="proj_1",
        )
    assert "still active" in str(exc_info.value)
