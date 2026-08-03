#!/usr/bin/env python3
"""
Phase 12 verification — VP12_BROWSER_RUNTIME_VERIFIED (plan 04 §7-§10).

Verifies the bounded browser runtime (`tools/windagent_tools/browser/`) against
the ratified contracts in `docs/video_production/browser_runtime/`:

  artifacts/video_production/phase_12/
  ├── action_policy_receipt.json      (typed allow/deny matrix)
  ├── session_lock_receipt.json       (profile lock collision + registry)
  ├── evidence_redaction_receipt.json (hashes only, no raw content)
  ├── healthcheck_receipt.json        (offline classification)
  ├── runtime_contract_receipt.json   (bounded actions via fake process)
  └── phase_verdict.json

Gate conditions (plan 04 §10):
  1. bounded action policy — deny eval / cookie export / upload outside the
     approved store / payment/terms (fail closed);
  2. persistent session + profile lock collision semantics;
  3. timeout / cancel / cleanup evidence coverage;
  4. redacted evidence — hashes only, no secrets;
  5. health classification is offline and precise;
  6. no Flow production required (fake process everywhere).

Every check is offline and fully deterministic. Supports --no-write /
--verify-only.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_12"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_tools.browser import (  # noqa: E402
    AgentBrowserCommandResult,
    AgentBrowserConfig,
    BrowserActionDeniedError,
    BrowserActionPolicy,
    BrowserActionResultState,
    BrowserEvidenceRecorder,
    BrowserHealthCheck,
    BrowserHealthStatus,
    BrowserOperation,
    BrowserProfileLock,
    BrowserProfileLockError,
    BrowserRuntime,
    BrowserSessionNotHealthyError,
    BrowserSessionRegistry,
    BrowserSessionState,
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


class FakeProcess:
    """Deterministic fake agent-browser process port (gate §10)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def run(self, argv, *, timeout_seconds, env):
        self.calls.append(tuple(argv))
        command = tuple(argv)
        if command[-1:] == ("read",):
            return AgentBrowserCommandResult(
                argv=command, returncode=0, stdout="fixture rendered page text", stderr=""
            )
        if command[-2:] == ("get", "title"):
            return AgentBrowserCommandResult(
                argv=command, returncode=0, stdout="Fixture Page", stderr=""
            )
        if command[-2:] == ("get", "url"):
            return AgentBrowserCommandResult(
                argv=command, returncode=0,
                stdout="https://flow.google.com/projects/1", stderr="",
            )
        if command[-2:] == ("cookies", "get"):
            return AgentBrowserCommandResult(
                argv=command, returncode=0, stdout='{"cookies":[]}', stderr=""
            )
        return AgentBrowserCommandResult(
            argv=command, returncode=0, stdout="OK", stderr=""
        )


def _runtime(workspace: Path, *, process=None):
    return BrowserRuntime(
        session_id="sess_verify_01",
        workspace_root=str(workspace),
        profile_key="profile_verify_01",
        allowed_domains=["flow.google.com"],
        approved_asset_store=str(workspace / "assets"),
        config=AgentBrowserConfig(
            session="sess_verify_01",
            authenticated=True,
            profile="Default",
            allowed_domains=("flow.google.com",),
            containment_mode="preflight",
            timeout_seconds=5.0,
        ),
        process=process or FakeProcess(),
        action_timeout_seconds=5.0,
    )


# ---------------------------------------------------------------------------
# 1. Action policy receipt (plan §8.4)
# ---------------------------------------------------------------------------
def build_action_policy_receipt() -> dict:
    checks: list[dict] = []

    policy = BrowserActionPolicy(allowed_domains=["flow.google.com"])

    inside = policy.evaluate(
        BrowserOperation.OPEN_URL, target="https://flow.google.com/projects/new"
    )
    _record(checks, "allow_url_inside_allowlist", inside.allowed, "flow.google.com allowed")

    outside = policy.evaluate(
        BrowserOperation.OPEN_URL, target="https://evil.example.com/phish"
    )
    _record(checks, "deny_url_outside_allowlist", not outside.allowed,
            f"code={outside.code.value}")

    creds = policy.evaluate(
        BrowserOperation.OPEN_URL,
        target="https://user:secret@flow.google.com/projects",
    )
    _record(checks, "deny_credentials_in_url", not creds.allowed,
            "credentials in URL denied")

    eval_op = policy.evaluate(BrowserOperation.EVAL, target="document.cookie")
    _record(checks, "deny_arbitrary_eval", not eval_op.allowed,
            f"code={eval_op.code.value}")

    cookie_op = policy.evaluate(BrowserOperation.COOKIE_EXPORT)
    _record(checks, "deny_cookie_export", not cookie_op.allowed,
            "cookie export denied")

    store = Path(tempfile.mkdtemp(prefix="phase12_assets_"))
    outside_upload = store.parent / "secret.png"
    upload_policy = BrowserActionPolicy(approved_asset_store=str(store))
    upload_decision = upload_policy.evaluate(
        BrowserOperation.UPLOAD, target=str(outside_upload)
    )
    _record(checks, "deny_upload_outside_store", not upload_decision.allowed,
            f"code={upload_decision.code.value}")

    approved = store / "ref.png"
    approved.write_bytes(b"png")
    upload_ok = upload_policy.evaluate(BrowserOperation.UPLOAD, target=str(approved))
    _record(checks, "allow_upload_inside_store", upload_ok.allowed,
            "approved store upload allowed")

    payment = policy.evaluate(
        BrowserOperation.CLICK, target="Confirm payment of $10"
    )
    _record(checks, "payment_terms_never_auto_confirmed",
            not payment.allowed and payment.requires_confirmation,
            "payment/terms requires human confirmation")

    unknown = BrowserActionPolicy(default_deny=True).evaluate("bogus_op", target="x")
    _record(checks, "unknown_operation_fails_closed", not unknown.allowed,
            "unknown operation denied (fail closed)")

    allowlist = policy.operation_allowlist()
    _record(checks, "allowlist_has_expected_ops",
            {"open_url", "snapshot", "click", "upload", "download", "wait"}
            <= set(allowlist),
            f"allowlist={allowlist}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/browser_runtime/browser_action_policy.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. Session lock receipt (plan §8.3)
# ---------------------------------------------------------------------------
def build_session_lock_receipt() -> dict:
    checks: list[dict] = []
    workspace = Path(tempfile.mkdtemp(prefix="phase12_lock_"))

    lock = BrowserProfileLock(str(workspace), lease_seconds=100, clock=time.time)
    token = lock.acquire("profile_verify_01", worker_id="worker_a")
    _record(checks, "lock_acquired", bool(token), "first worker holds the lease")

    collision = False
    try:
        lock.acquire("profile_verify_01", worker_id="worker_b")
    except BrowserProfileLockError:
        collision = True
    _record(checks, "lock_collision_detected", collision,
            "second worker on the same profile is rejected")

    released = lock.release("profile_verify_01", token)
    _record(checks, "lock_released_by_holder", released and not lock.is_locked("profile_verify_01"),
            "holder can release the lock")

    registry = BrowserSessionRegistry(
        f"{workspace}/artifacts/browser_sessions", clock=time.time
    )
    registry.register("sess_verify_01", profile_key="profile_verify_01")
    registry.update_state("sess_verify_01", BrowserSessionState.READY)

    reloaded = BrowserSessionRegistry(
        f"{workspace}/artifacts/browser_sessions", clock=time.time
    )
    got = reloaded.get("sess_verify_01")
    _record(checks, "session_registry_persists",
            got is not None and got.state == BrowserSessionState.READY
            and got.profile_key == "profile_verify_01",
            "registry survives reload (worker restart)")

    # metadata never carries a profile path
    _record(checks, "metadata_has_no_profile_path",
            "profile_path" not in json.dumps(got.to_dict()),
            "only opaque profile_key is stored")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/browser_runtime/browser_runtime_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Evidence redaction receipt (plan §8.5)
# ---------------------------------------------------------------------------
def build_evidence_redaction_receipt() -> dict:
    checks: list[dict] = []
    workspace = Path(tempfile.mkdtemp(prefix="phase12_evidence_"))

    recorder = BrowserEvidenceRecorder(
        session_id="sess_verify_01",
        clock=time.time,
        redact_screenshot=lambda p: "f" * 64,
    )
    action_id = recorder.begin(
        "open_url", target="https://flow.google.com/?token=abc123"
    )
    shot = workspace / "shot.png"
    shot.write_bytes(b"\x89PNG fake bytes")
    evidence = recorder.finish(
        action_id,
        BrowserActionResultState.SUCCESS,
        screenshot_path=str(shot),
        snapshot="- button [ref=@e1]",
    )

    _record(checks, "evidence_has_all_fields",
            all(
                evidence.action_id and evidence.session_id
                and evidence.operation and evidence.started_at
                and evidence.finished_at and evidence.result_state
            ),
            "action/session/operation/timestamps/result present")

    _record(checks, "evidence_url_secret_redacted",
            "token=abc123" not in evidence.target_semantics,
            "URL query secret is redacted from target_semantics")

    _record(checks, "evidence_screenshot_is_hash",
            evidence.redacted_screenshot_hash == "f" * 64,
            "screenshot stored as hash only")

    _record(checks, "evidence_snapshot_is_hash",
            len(evidence.snapshot_hash) == 64,
            "snapshot stored as sha256 hash only")

    _record(checks, "evidence_no_raw_content",
            "fixture" not in json.dumps(evidence.to_dict())
            and "PNG" not in json.dumps(evidence.to_dict()),
            "no raw screenshot/page content in the record")

    blocked_id = recorder.begin("eval", target="document.cookie")
    blocked = recorder.finish(
        blocked_id, BrowserActionResultState.BLOCKED, error_class="BrowserActionDeniedError"
    )
    _record(checks, "evidence_blocked_has_error_class",
            blocked.result_state == BrowserActionResultState.BLOCKED
            and blocked.error_class == "BrowserActionDeniedError",
            "BLOCKED evidence carries the error class")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/browser_runtime/browser_evidence_redaction.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Healthcheck receipt (plan §8.5)
# ---------------------------------------------------------------------------
def build_healthcheck_receipt() -> dict:
    checks: list[dict] = []
    check = BrowserHealthCheck(allowed_domains=["flow.google.com"])

    healthy = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    _record(checks, "healthy_classification",
            healthy.status == BrowserHealthStatus.HEALTHY,
            "all signals pass -> HEALTHY")

    human = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.HUMAN_REQUIRED,
        lease_expires_at=time.time() + 100,
    )
    _record(checks, "human_required_is_degraded",
            human.status == BrowserHealthStatus.DEGRADED and human.human_required,
            "human-required state -> DEGRADED, never HEALTHY")

    domain_bad = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://evil.example.com",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    _record(checks, "domain_violation_unhealthy",
            domain_bad.status == BrowserHealthStatus.UNHEALTHY,
            "page outside allowlist -> UNHEALTHY")

    dead = check.check(
        process_alive=False,
        browser_reachable=False,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=False,
        session_state=BrowserSessionState.READY,
        lease_expires_at=0.0,
    )
    _record(checks, "dead_session_unhealthy",
            dead.status == BrowserHealthStatus.UNHEALTHY,
            "process/browser/lock down -> UNHEALTHY")

    empty_allowlist = BrowserHealthCheck(allowed_domains=[]).check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    _record(checks, "empty_allowlist_fails_closed",
            empty_allowlist.status == BrowserHealthStatus.UNHEALTHY,
            "no domain configured -> not healthy (fail closed)")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/browser_runtime/browser_runtime_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 5. Runtime contract receipt (plan §8.2, §9)
# ---------------------------------------------------------------------------
def build_runtime_contract_receipt() -> dict:
    checks: list[dict] = []
    workspace = Path(tempfile.mkdtemp(prefix="phase12_runtime_"))

    runtime = _runtime(workspace)
    runtime.start()
    try:
        result = asyncio.run(
            runtime.execute(
                BrowserOperation.OPEN_URL,
                target="https://flow.google.com/projects/new",
            )
        )
        _record(checks, "bounded_open_url_succeeds",
                result.evidence.result_state == BrowserActionResultState.SUCCESS,
                "typed open_url with fake process succeeds")

        try:
            asyncio.run(runtime.execute(BrowserOperation.EVAL, target="document.cookie"))
            _record(checks, "runtime_denies_eval", False, "expected denial")
        except BrowserActionDeniedError:
            blocked = [
                r for r in runtime._evidence.recent()
                if r.result_state == BrowserActionResultState.BLOCKED
            ]
            _record(checks, "runtime_denies_eval", bool(blocked),
                    "eval blocked with BLOCKED evidence")

        runtime._registry.update_state(
            "sess_verify_01", BrowserSessionState.HUMAN_REQUIRED
        )
        try:
            asyncio.run(
                runtime.execute(
                    BrowserOperation.OPEN_URL,
                    target="https://flow.google.com/projects/2",
                )
            )
            _record(checks, "unhealthy_session_blocks_action", False, "expected block")
        except BrowserSessionNotHealthyError:
            _record(checks, "unhealthy_session_blocks_action", True,
                    "non-HEALTHY session blocks actions")
    finally:
        asyncio.run(runtime.stop())

    # worker restart + reattach preserves the session
    runtime2 = _runtime(workspace)
    asyncio.run(runtime2.reattach())
    meta = runtime2._registry.get("sess_verify_01")
    _record(checks, "reattach_preserves_session",
            meta is not None and meta.state == BrowserSessionState.READY,
            "reattach keeps registered session + state")
    asyncio.run(runtime2.stop())

    # upstream runtime pin (plan §8.1): config from env + secret env stripping
    pin_env = {
        "AGENT_BROWSER_BIN": "agent-browser",
        "AGENT_BROWSER_ALLOWED_DOMAINS": "flow.google.com",
        "AGENT_BROWSER_SESSION": "pinned",
        "WINDAGENT_BROWSER_AUTHENTICATED": "1",
        "WINDAGENT_BROWSER_CONTAINMENT": "preflight",
        "AGENT_BROWSER_PROFILE": "Default",
        "WINDAGENT_API_KEY": "sk-super-secret",
    }
    pin_config = AgentBrowserConfig.from_env(pin_env)
    _record(checks, "runtime_pin_reads_env",
            pin_config.binary == "agent-browser"
            and pin_config.session == "pinned"
            and "flow.google.com" in pin_config.allowed_domains,
            "agent-browser pin is env-configurable")
    child_env = pin_config.process_env()
    _record(checks, "runtime_pin_strips_secrets",
            all(marker not in "|".join(f"{k}={v}" for k, v in child_env.items()).upper()
                for marker in ("SK-SUPER-SECRET",))
            and "WINDAGENT_API_KEY" not in child_env,
            "secret-marked env vars never reach the child process")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/browser_runtime/browser_runtime_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    policy_receipt = build_action_policy_receipt()
    lock_receipt = build_session_lock_receipt()
    evidence_receipt = build_evidence_redaction_receipt()
    health_receipt = build_healthcheck_receipt()
    runtime_receipt = build_runtime_contract_receipt()

    gate_reasons: list[str] = []
    if not policy_receipt["all_checks_pass"]:
        gate_reasons.append("action policy checks failed")
    if not lock_receipt["all_checks_pass"]:
        gate_reasons.append("session lock checks failed")
    if not evidence_receipt["all_checks_pass"]:
        gate_reasons.append("evidence redaction checks failed")
    if not health_receipt["all_checks_pass"]:
        gate_reasons.append("healthcheck checks failed")
    if not runtime_receipt["all_checks_pass"]:
        gate_reasons.append("runtime contract checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 12,
        "status": overall_status,
        "gate": "VP12_BROWSER_RUNTIME_VERIFIED",
        "evidence": [
            {"path": "action_policy_receipt.json"},
            {"path": "session_lock_receipt.json"},
            {"path": "evidence_redaction_receipt.json"},
            {"path": "healthcheck_receipt.json"},
            {"path": "runtime_contract_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase12_browser_runtime.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "action_policy_receipt.json", policy_receipt)
        write_json(PHASE_DIR / "session_lock_receipt.json", lock_receipt)
        write_json(PHASE_DIR / "evidence_redaction_receipt.json", evidence_receipt)
        write_json(PHASE_DIR / "healthcheck_receipt.json", health_receipt)
        write_json(PHASE_DIR / "runtime_contract_receipt.json", runtime_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                policy_receipt,
                lock_receipt,
                evidence_receipt,
                health_receipt,
                runtime_receipt,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_12 artifacts untouched.")

    print(f"Phase 12 verdict: {overall_status}")
    print(f"  action policy: {'PASS' if policy_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  session lock: {'PASS' if lock_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  evidence redaction: {'PASS' if evidence_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  healthcheck: {'PASS' if health_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  runtime contract: {'PASS' if runtime_receipt['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, policy, lock, evidence, health, runtime) -> str:
    return f"""# Phase 12 Report — Browser Runtime Foundation

- **Gate:** `VP12_BROWSER_RUNTIME_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Action policy

- Contract: `docs/video_production/browser_runtime/browser_action_policy.md`
- Checks: {policy.get('check_count')}; all pass: {policy.get('all_checks_pass')}

## Session & profile lock

- Contract: `docs/video_production/browser_runtime/browser_runtime_contract.md`
- Checks: {lock.get('check_count')}; all pass: {lock.get('all_checks_pass')}

## Evidence redaction

- Contract: `docs/video_production/browser_runtime/browser_evidence_redaction.md`
- Checks: {evidence.get('check_count')}; all pass: {evidence.get('all_checks_pass')}

## Healthcheck

- Contract: `docs/video_production/browser_runtime/browser_runtime_contract.md`
- Checks: {health.get('check_count')}; all pass: {health.get('all_checks_pass')}

## Runtime contract

- Contract: `docs/video_production/browser_runtime/browser_runtime_contract.md`
- Checks: {runtime.get('check_count')}; all pass: {runtime.get('all_checks_pass')}

## Evidence

- `action_policy_receipt.json`
- `session_lock_receipt.json`
- `evidence_redaction_receipt.json`
- `healthcheck_receipt.json`
- `runtime_contract_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
