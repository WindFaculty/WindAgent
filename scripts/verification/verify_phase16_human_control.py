#!/usr/bin/env python3
"""
Phase 16 verification — VP16_FLOW_HUMAN_CONTROL_VERIFIED (plan 04 §25–§28).

Verifies human intervention and account safety adapters (`tools/windagent_tools/google_flow/human_control.py`)
against the contracts in `docs/video_production/flow_human_control/`:

  artifacts/video_production/phase_16/
  ├── human_states_receipt.json          (5 typed human states + fail-closed)
  ├── pause_takeover_receipt.json        (session pause, takeover instructions)
  ├── resume_reconciliation_receipt.json (6-step safe resume, zero duplicate submit)
  ├── account_safety_receipt.json       (zero-bypass rule, evidence redaction, circuit breaker)
  └── phase_verdict.json

Gate conditions (plan 04 §28):
  1. All challenges in scope transfer to typed human states without bypass paths.
  2. Takeover pauses worker actions while preserving session profile locks.
  3. Resume protocol verifies challenge clearance, account/project identity, and job reconciliation without duplicate submits.
  4. Account safety policy enforces evidence redaction, zero-bypass, and circuit breaker tripping.

Supports --no-write / --verify-only.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_16"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_tools.google_flow import (  # noqa: E402
    FlowAccountSafetyPolicy,
    FlowCircuitBreakerTrippedError,
    FlowConcurrencyLimitExceededError,
    FlowHumanActionBlockedError,
    FlowHumanActionStatus,
    FlowHumanBypassAttemptedError,
    FlowHumanControlDetector,
    FlowHumanControlError,
    FlowHumanControlManager,
    FlowHumanState,
    FlowJobRegistry,
    FlowJobStatus,
    FlowRateLimitExceededError,
    FlowUiObservation,
    FlowUiState,
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


def verify_human_states() -> dict:
    checks = []

    # 1. Login
    obs_login = FlowUiObservation(url="https://accounts.google.com/signin", markers=("Choose an account",))
    st_login = FlowHumanControlDetector.detect(obs_login)
    _record(checks, "detect_login", st_login == FlowHumanState.HUMAN_LOGIN_REQUIRED, f"got {st_login}")

    # 2. CAPTCHA
    obs_captcha = FlowUiObservation(url="https://flow.google.com", markers=("recaptcha challenge",))
    st_captcha = FlowHumanControlDetector.detect(obs_captcha)
    _record(checks, "detect_captcha", st_captcha == FlowHumanState.HUMAN_CAPTCHA_REQUIRED, f"got {st_captcha}")

    # 3. Account Verification
    obs_verif = FlowUiObservation(url="https://flow.google.com", markers=("2-step verification",))
    st_verif = FlowHumanControlDetector.detect(obs_verif)
    _record(checks, "detect_account_verification", st_verif == FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED, f"got {st_verif}")

    # 4. Payment Confirmation
    obs_pay = FlowUiObservation(url="https://flow.google.com/billing", markers=("buy credits",))
    st_pay = FlowHumanControlDetector.detect(obs_pay)
    _record(checks, "detect_payment_confirmation", st_pay == FlowHumanState.HUMAN_PAYMENT_CONFIRMATION_REQUIRED, f"got {st_pay}")

    # 5. Terms Acceptance
    obs_terms = FlowUiObservation(url="https://flow.google.com/terms", markers=("accept terms",))
    st_terms = FlowHumanControlDetector.detect(obs_terms)
    _record(checks, "detect_terms_acceptance", st_terms == FlowHumanState.HUMAN_TERMS_ACCEPTANCE_REQUIRED, f"got {st_terms}")

    # 6. Unknown challenge fail-closed
    obs_unknown = FlowUiObservation(url="https://accounts.google.com/unknown_challenge", markers=("security check",))
    st_unknown = FlowHumanControlDetector.detect(obs_unknown, expected_state=FlowUiState.SUBMIT_READY)
    _record(checks, "unknown_challenge_fail_closed", st_unknown is not None, f"got {st_unknown}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP16_FLOW_HUMAN_CONTROL_VERIFIED",
        "workstream": "human_states",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


def verify_pause_takeover() -> dict:
    checks = []
    state_dir = tempfile.mkdtemp()
    manager = FlowHumanControlManager(state_dir=state_dir)

    # Create action record & pause session
    record = manager.create_human_action(
        session_id="sess_v16",
        project_id="vp_1",
        human_state=FlowHumanState.HUMAN_CAPTCHA_REQUIRED,
        reason="CAPTCHA challenge on navigation",
        safe_resume_state=FlowUiState.PROJECT_OPEN,
        raw_evidence={"url": "https://flow.google.com", "cookie": "secret_123"},
    )
    _record(checks, "record_creation", record.status == FlowHumanActionStatus.PENDING, f"id={record.human_action_id}")

    # Session pause check
    blocked = False
    try:
        manager.assert_session_active("sess_v16")
    except FlowHumanActionBlockedError:
        blocked = True
    _record(checks, "session_paused_blocked_actions", blocked, "FlowHumanActionBlockedError raised as expected")

    # Takeover instructions check (secrets omitted)
    instr = manager.get_takeover_instructions(record.human_action_id)
    no_secret = "secret_123" not in str(instr)
    _record(checks, "takeover_instructions_no_secrets", no_secret and "user_action_required" in instr, "instructions clean")

    # Durable pause survives a worker restart; a new process must not be able
    # to keep driving this browser session while the operator has control.
    reloaded = FlowHumanControlManager(state_dir=state_dir)
    restored = reloaded.get_record(record.human_action_id)
    restored_blocked = False
    try:
        reloaded.assert_session_active("sess_v16")
    except FlowHumanActionBlockedError:
        restored_blocked = True
    _record(
        checks,
        "durable_pause_survives_reload",
        restored is not None
        and restored.status == FlowHumanActionStatus.PENDING
        and restored_blocked,
        "pending takeover is restored and still blocks automation",
    )

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP16_FLOW_HUMAN_CONTROL_VERIFIED",
        "workstream": "pause_takeover",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


def verify_resume_reconciliation() -> dict:
    checks = []
    state_dir = tempfile.mkdtemp()
    manager = FlowHumanControlManager(state_dir=state_dir)
    registry = FlowJobRegistry(state_dir=state_dir)

    # Prepare submitting job
    registry.create_prepared(
        generation_id="gen_v16",
        project_id="vp_1",
        revision_id="rev_1",
        shot_id="shot_1",
        provider="google_flow_browser",
        request_hash="f" * 64,
        browser_session_id="sess_rec",
        flow_project_id="flow_p1",
    )
    registry.mark("gen_v16", FlowJobStatus.SUBMITTING)

    record = manager.create_human_action(
        session_id="sess_rec",
        project_id="vp_1",
        human_state=FlowHumanState.HUMAN_CAPTCHA_REQUIRED,
        reason="CAPTCHA challenge",
        safe_resume_state=FlowUiState.PROJECT_OPEN,
        raw_evidence={"url": "https://flow.google.com"},
        generation_id="gen_v16",
    )

    # 1. Resume fails if challenge active
    dirty_obs = FlowUiObservation(url="https://flow.google.com", markers=("recaptcha challenge",))
    challenge_fail = False
    try:
        manager.execute_safe_resume(record.human_action_id, "op_1", dirty_obs, "vp_1", registry)
    except FlowHumanControlError as e:
        if "still active" in str(e):
            challenge_fail = True
    _record(checks, "resume_fails_when_challenge_active", challenge_fail, "blocked active challenge")

    # 2. Resume succeeds when clean & reconciles job
    clean_obs = FlowUiObservation(url="https://flow.google.com/p1", markers=("create workspace", "editor ready"))
    audit = manager.execute_safe_resume(
        record.human_action_id,
        "op_1",
        clean_obs,
        "vp_1",
        registry,
        project_verifier=lambda project_id, _: project_id == "vp_1",
    )
    reconciled_job = registry.get("gen_v16")
    job_status_val = reconciled_job.status if reconciled_job else FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION
    _record(checks, "safe_resume_success", record.status == FlowHumanActionStatus.RESOLVED, "action resolved")
    _record(checks, "job_reconciled_no_dup_submit", job_status_val == FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION, f"status={job_status_val.value}")
    reloaded = FlowHumanControlManager(state_dir=state_dir)
    session_unpaused = True
    try:
        reloaded.assert_session_active("sess_rec")
    except FlowHumanActionBlockedError:
        session_unpaused = False
    _record(
        checks,
        "durable_resolution_unpauses_session",
        session_unpaused
        and reloaded.get_record(record.human_action_id).status == FlowHumanActionStatus.RESOLVED
        and audit["project_verified"],
        "resolved action persisted with verified project and active session",
    )

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP16_FLOW_HUMAN_CONTROL_VERIFIED",
        "workstream": "resume_reconciliation",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


def verify_account_safety() -> dict:
    checks = []
    policy = FlowAccountSafetyPolicy(max_interventions_per_session=2)

    # 1. Zero bypass enforcement
    bypass_blocked = False
    try:
        policy.assert_no_automated_bypass("ocr_captcha_solver")
    except FlowHumanBypassAttemptedError:
        bypass_blocked = True
    _record(checks, "zero_bypass_enforced", bypass_blocked, "bypassed action blocked")

    # 2. Evidence redaction
    raw_ev = {
        "user": "operator@test.com",
        "auth_header": "Bearer secret_jwt_token",
        "cookie": "session_id=12345",
        "card_num": "4111-1111-1111-1111",
        "label": "visible_text",
    }
    redacted = FlowAccountSafetyPolicy.redact_dict(raw_ev)
    redacted_ok = (
        redacted["user"] == "[REDACTED]"
        and redacted["auth_header"] == "[REDACTED_SECRET]"
        and redacted["cookie"] == "[REDACTED_SECRET]"
        and redacted["card_num"] == "[REDACTED]"
        and redacted["label"] == "visible_text"
    )
    _record(checks, "evidence_redaction_sanitizes_secrets", redacted_ok, "redaction clean")

    # 3. Circuit breaker tripping
    policy.record_intervention("sess_cb")
    policy.record_intervention("sess_cb")
    cb_tripped = False
    try:
        policy.record_intervention("sess_cb")
    except FlowCircuitBreakerTrippedError:
        cb_tripped = True
    _record(checks, "circuit_breaker_trips_on_limit", cb_tripped, "circuit breaker tripped")

    # 4. Concrete concurrency enforcement: a competing browser operation is
    # denied while the only account slot is reserved.
    now = [1_000.0]
    concurrency_manager = FlowHumanControlManager(
        safety_policy=FlowAccountSafetyPolicy(
            max_concurrency=1, rate_limit_per_minute=10, clock=lambda: now[0]
        )
    )
    concurrency_manager.begin_automated_action("sess_concurrent_a", "op_a")
    concurrency_blocked = False
    try:
        concurrency_manager.begin_automated_action("sess_concurrent_b", "op_b")
    except FlowConcurrencyLimitExceededError:
        concurrency_blocked = True
    concurrency_manager.end_automated_action("sess_concurrent_a", "op_a")
    _record(checks, "concurrency_limit_enforced", concurrency_blocked, "competing action denied")

    # 5. Concrete rate enforcement: releasing capacity does not reset the
    # per-minute action budget.
    rate_manager = FlowHumanControlManager(
        safety_policy=FlowAccountSafetyPolicy(
            max_concurrency=1, rate_limit_per_minute=1, clock=lambda: now[0]
        )
    )
    rate_manager.begin_automated_action("sess_rate", "op_1")
    rate_manager.end_automated_action("sess_rate", "op_1")
    rate_blocked = False
    try:
        rate_manager.begin_automated_action("sess_rate", "op_2")
    except FlowRateLimitExceededError:
        rate_blocked = True
    now[0] += 60.0
    rate_manager.begin_automated_action("sess_rate", "op_3")
    rate_manager.end_automated_action("sess_rate", "op_3")
    _record(checks, "rate_limit_enforced", rate_blocked, "same-session burst denied")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP16_FLOW_HUMAN_CONTROL_VERIFIED",
        "workstream": "account_safety",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


def main(no_write: bool = False) -> int:
    print("Verifying Phase 16 — Human Intervention and Account Safety...")
    human_states = verify_human_states()
    pause_takeover = verify_pause_takeover()
    resume_rec = verify_resume_reconciliation()
    acc_safety = verify_account_safety()

    all_workstreams = [human_states, pause_takeover, resume_rec, acc_safety]
    overall_pass = all(w["all_checks_pass"] for w in all_workstreams)
    overall_status = "PASSED" if overall_pass else "FAILED"

    gate_reasons = []
    if not overall_pass:
        for w in all_workstreams:
            if not w["all_checks_pass"]:
                for c in w["checks"]:
                    if not c["ok"]:
                        gate_reasons.append(f"[{w['workstream']}] {c['check']}: {c['detail']}")

    verdict = {
        "gate": "VP16_FLOW_HUMAN_CONTROL_VERIFIED",
        "status": overall_status,
        "verified_at": utc_now_iso(),
        "workstreams": {
            "human_states": human_states["all_checks_pass"],
            "pause_takeover": pause_takeover["all_checks_pass"],
            "resume_reconciliation": resume_rec["all_checks_pass"],
            "account_safety": acc_safety["all_checks_pass"],
        },
        "blocking_reasons": gate_reasons,
    }

    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(PHASE_DIR / "human_states_receipt.json", human_states)
        write_json(PHASE_DIR / "pause_takeover_receipt.json", pause_takeover)
        write_json(PHASE_DIR / "resume_reconciliation_receipt.json", resume_rec)
        write_json(PHASE_DIR / "account_safety_receipt.json", acc_safety)
        write_json(PHASE_DIR / "phase_verdict.json", verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, human_states, pause_takeover, resume_rec, acc_safety),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_16 artifacts untouched.")

    print(f"Phase 16 verdict: {overall_status}")
    print(f"  human states: {'PASS' if human_states['all_checks_pass'] else 'FAIL'}")
    print(f"  pause takeover: {'PASS' if pause_takeover['all_checks_pass'] else 'FAIL'}")
    print(f"  resume reconciliation: {'PASS' if resume_rec['all_checks_pass'] else 'FAIL'}")
    print(f"  account safety: {'PASS' if acc_safety['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, states, pause, resume, safety) -> str:
    return f"""# Phase 16 Report — Human Intervention and Account Safety

- **Gate:** `VP16_FLOW_HUMAN_CONTROL_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Human States Detection

- Contract: `docs/video_production/flow_human_control/human_states_contract.md`
- Checks: {states.get('check_count')}; all pass: {states.get('all_checks_pass')}

## Pause & Takeover Management

- Contract: `docs/video_production/flow_human_control/human_states_contract.md`
- Checks: {pause.get('check_count')}; all pass: {pause.get('all_checks_pass')}

## Safe Resume Protocol & Job Reconciliation

- Contract: `docs/video_production/flow_human_control/resume_reconciliation_contract.md`
- Checks: {resume.get('check_count')}; all pass: {resume.get('all_checks_pass')}

## Account Safety & Zero-Bypass Policy

- Contract: `docs/video_production/flow_human_control/account_safety_contract.md`
- Checks: {safety.get('check_count')}; all pass: {safety.get('all_checks_pass')}

## Evidence

- `human_states_receipt.json`
- `pause_takeover_receipt.json`
- `resume_reconciliation_receipt.json`
- `account_safety_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
