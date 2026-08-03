"""Phase 12 — Browser runtime foundation unit tests (plan 04 §8–§10).

Covers: action policy allow/deny, profile lock collision, session registry,
evidence redaction, health classification, runtime bounded actions, cancel,
timeout, reattach — all with a fake process (no Chrome / no Flow production).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from windagent_tools.browser import (
    AgentBrowserCommandResult,
    AgentBrowserConfig,
    BrowserActionDeniedError,
    BrowserActionPolicy,
    BrowserActionResultState,
    BrowserActionTimeoutError,
    BrowserEvidenceRecorder,
    BrowserHealthCheck,
    BrowserHealthStatus,
    BrowserOperation,
    BrowserProfileLock,
    BrowserProfileLockError,
    BrowserRuntime,
    BrowserRuntimeError,
    BrowserSessionNotHealthyError,
    BrowserSessionRegistry,
    BrowserSessionState,
)


class FakeProcess:
    """Deterministic fake agent-browser process port."""

    def __init__(self, *, delay_open_seconds: float = 0.0) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.raise_timeout = False
        self.delay_open_seconds = delay_open_seconds

    async def run(self, argv, *, timeout_seconds, env):
        self.calls.append(tuple(argv))
        command = tuple(argv)
        if self.raise_timeout:
            raise TimeoutError("fake timeout")
        if (
            self.delay_open_seconds
            and len(command) >= 2
            and command[-2] == "open"
        ):
            # Block mid-action so cancellation lands while the action is
            # still in flight (the default fake is fully synchronous).
            # argv is ``[..., subcommand, arg]`` for ``open <url>``.
            await asyncio.sleep(self.delay_open_seconds)
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
                argv=command, returncode=0, stdout="https://flow.google.com/projects/1", stderr=""
            )
        if command[-2:] == ("cookies", "get"):
            return AgentBrowserCommandResult(
                argv=command, returncode=0, stdout='{"cookies":[]}', stderr=""
            )
        if command[-1:] == ("snapshot",):
            return AgentBrowserCommandResult(
                argv=command, returncode=0, stdout='- button "Submit" [ref=@e1]', stderr=""
            )
        return AgentBrowserCommandResult(argv=command, returncode=0, stdout="OK", stderr="")


def _runtime(tmp_path: Path, **kwargs):
    process = kwargs.pop("process", None) or FakeProcess()
    allowed_domains = kwargs.pop("allowed_domains", ["flow.google.com"])
    action_timeout_seconds = kwargs.pop("action_timeout_seconds", 5.0)
    return (
        BrowserRuntime(
            session_id="sess_test_01",
            workspace_root=str(tmp_path),
            profile_key="profile_test_01",
            allowed_domains=allowed_domains,
            config=AgentBrowserConfig(
                session="sess_test_01",
                authenticated=True,
                profile="Default",
                allowed_domains=tuple(allowed_domains),
                containment_mode="preflight",
                timeout_seconds=5.0,
            ),
            process=process,
            action_timeout_seconds=action_timeout_seconds,
            **kwargs,
        ),
        process,
    )


# ---------------------------------------------------------------------------
# Action policy
# ---------------------------------------------------------------------------
def test_policy_allow_open_url_inside_allowlist():
    policy = BrowserActionPolicy(allowed_domains=["flow.google.com"])
    decision = policy.evaluate(
        BrowserOperation.OPEN_URL, target="https://flow.google.com/projects/new"
    )
    assert decision.allowed


def test_policy_deny_navigation_outside_allowlist():
    policy = BrowserActionPolicy(allowed_domains=["flow.google.com"])
    decision = policy.evaluate(
        BrowserOperation.OPEN_URL, target="https://evil.example.com/phish"
    )
    assert not decision.allowed
    assert decision.code.value == "deny_domain"


def test_policy_deny_credentials_in_url():
    policy = BrowserActionPolicy(allowed_domains=["flow.google.com"])
    decision = policy.evaluate(
        BrowserOperation.OPEN_URL,
        target="https://user:secret@flow.google.com/projects",
    )
    assert not decision.allowed


def test_policy_deny_arbitrary_eval():
    policy = BrowserActionPolicy()
    decision = policy.evaluate(BrowserOperation.EVAL, target="document.cookie")
    assert not decision.allowed
    assert decision.code.value == "deny_operation"


def test_policy_deny_cookie_export():
    policy = BrowserActionPolicy()
    decision = policy.evaluate(BrowserOperation.COOKIE_EXPORT)
    assert not decision.allowed


def test_policy_deny_upload_outside_approved_store(tmp_path):
    store = tmp_path / "assets"
    store.mkdir()
    outside = tmp_path / "private" / "secret.png"
    policy = BrowserActionPolicy(approved_asset_store=str(store))
    decision = policy.evaluate(BrowserOperation.UPLOAD, target=str(outside))
    assert not decision.allowed
    assert decision.code.value == "deny_upload_path"


def test_policy_allow_upload_inside_approved_store(tmp_path):
    store = tmp_path / "assets"
    store.mkdir()
    approved = store / "reference.png"
    approved.write_bytes(b"png")
    policy = BrowserActionPolicy(approved_asset_store=str(store))
    decision = policy.evaluate(BrowserOperation.UPLOAD, target=str(approved))
    assert decision.allowed


def test_policy_payment_terms_requires_confirmation():
    policy = BrowserActionPolicy()
    decision = policy.evaluate(
        BrowserOperation.CLICK, target="Confirm payment of $10"
    )
    assert not decision.allowed
    assert decision.requires_confirmation
    assert decision.code.value == "require_confirmation"


def test_policy_deny_unknown_operation_fail_closed():
    policy = BrowserActionPolicy(default_deny=True)
    decision = policy.evaluate("not_a_real_operation", target="x")
    assert not decision.allowed


# ---------------------------------------------------------------------------
# Profile lock
# ---------------------------------------------------------------------------
def test_profile_lock_collision(tmp_path):
    lock = BrowserProfileLock(str(tmp_path), lease_seconds=100, clock=time.time)
    token = lock.acquire("profile_key_1", worker_id="worker_a")
    assert token
    assert lock.is_locked("profile_key_1")
    with pytest.raises(BrowserProfileLockError):
        lock.acquire("profile_key_1", worker_id="worker_b")


def test_profile_lock_release_only_holder(tmp_path):
    lock = BrowserProfileLock(str(tmp_path), lease_seconds=100, clock=time.time)
    token = lock.acquire("profile_key_1", worker_id="worker_a")
    # a different token cannot release
    assert not lock.release("profile_key_1", "worker_b:deadbeef1234")
    assert lock.is_locked("profile_key_1")
    # the holder can
    assert lock.release("profile_key_1", token)
    assert not lock.is_locked("profile_key_1")


def test_profile_lock_stale_lease_can_be_broken(tmp_path):
    fake_clock = [1000.0]
    lock = BrowserProfileLock(str(tmp_path), lease_seconds=10, clock=lambda: fake_clock[0])
    lock.acquire("profile_key_1", worker_id="worker_a")
    fake_clock[0] = 1100.0  # lease expired
    # new worker can break the stale lock
    token = lock.acquire("profile_key_1", worker_id="worker_b")
    assert token


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------
def test_session_registry_roundtrip(tmp_path):
    registry = BrowserSessionRegistry(str(tmp_path), clock=time.time)
    meta = registry.register("sess_a", profile_key="profile_a")
    assert meta.session_id == "sess_a"
    assert meta.state == BrowserSessionState.NEW

    updated = registry.update_state("sess_a", BrowserSessionState.READY)
    assert updated.state == BrowserSessionState.READY

    reloaded = BrowserSessionRegistry(str(tmp_path), clock=time.time)
    got = reloaded.get("sess_a")
    assert got is not None
    assert got.state == BrowserSessionState.READY
    assert got.profile_key == "profile_a"


def test_session_registry_duplicate_rejected(tmp_path):
    registry = BrowserSessionRegistry(str(tmp_path), clock=time.time)
    registry.register("sess_a")
    with pytest.raises(Exception):
        registry.register("sess_a")


# ---------------------------------------------------------------------------
# Evidence recorder
# ---------------------------------------------------------------------------
def test_evidence_record_redacts_content_to_hashes(tmp_path):
    recorder = BrowserEvidenceRecorder(
        session_id="sess_a", clock=time.time, redact_screenshot=lambda p: "f" * 64
    )
    action_id = recorder.begin("open_url", target="https://flow.google.com/?token=abc123")
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG fake")
    evidence = recorder.finish(
        action_id,
        BrowserActionResultState.SUCCESS,
        screenshot_path=str(shot),
        snapshot="- button [ref=@e1]",
    )
    assert evidence.action_id == action_id
    assert "token=abc123" not in evidence.target_semantics  # redacted
    assert evidence.redacted_screenshot_hash == "f" * 64
    assert len(evidence.snapshot_hash) == 64
    assert evidence.result_state == BrowserActionResultState.SUCCESS


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
def test_health_classification_healthy():
    check = BrowserHealthCheck(allowed_domains=["flow.google.com"])
    report = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    assert report.status == BrowserHealthStatus.HEALTHY


def test_health_classification_human_required_is_degraded():
    check = BrowserHealthCheck(allowed_domains=["flow.google.com"])
    report = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.HUMAN_REQUIRED,
        lease_expires_at=time.time() + 100,
    )
    assert report.status == BrowserHealthStatus.DEGRADED
    assert report.human_required


def test_health_classification_domain_violation_unhealthy():
    check = BrowserHealthCheck(allowed_domains=["flow.google.com"])
    report = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://evil.example.com",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    assert report.status == BrowserHealthStatus.UNHEALTHY


def test_health_empty_allowlist_fails_closed():
    check = BrowserHealthCheck(allowed_domains=[])
    report = check.check(
        process_alive=True,
        browser_reachable=True,
        current_url="https://flow.google.com/projects/1",
        profile_lock_valid=True,
        session_state=BrowserSessionState.READY,
        lease_expires_at=time.time() + 100,
    )
    assert report.status == BrowserHealthStatus.UNHEALTHY


# ---------------------------------------------------------------------------
# Runtime bounded actions
# ---------------------------------------------------------------------------
def test_runtime_open_url_succeeds_with_evidence(tmp_path):
    runtime, process = _runtime(tmp_path)
    runtime.start()
    try:
        result = asyncio.run(
            runtime.execute(
                BrowserOperation.OPEN_URL,
                target="https://flow.google.com/projects/new",
            )
        )
        assert result.evidence.result_state == BrowserActionResultState.SUCCESS
        assert result.final_url == "https://flow.google.com/projects/1"
        assert result.captured_text == "fixture rendered page text"
    finally:
        asyncio.run(runtime.stop())


def test_runtime_denied_action_fails_closed(tmp_path):
    runtime, process = _runtime(tmp_path)
    runtime.start()
    try:
        with pytest.raises(BrowserActionDeniedError):
            asyncio.run(
                runtime.execute(BrowserOperation.EVAL, target="document.cookie")
            )
        # evidence still recorded as BLOCKED
        blocked = [r for r in runtime._evidence.recent() if r.result_state == BrowserActionResultState.BLOCKED]
        assert blocked
    finally:
        asyncio.run(runtime.stop())


def test_runtime_requires_start_before_execute(tmp_path):
    runtime, process = _runtime(tmp_path)
    with pytest.raises(BrowserRuntimeError):
        asyncio.run(
            runtime.execute(BrowserOperation.OPEN_URL, target="https://flow.google.com/")
        )


def test_runtime_unhealthy_session_blocks_action(tmp_path):
    runtime, process = _runtime(tmp_path, allowed_domains=["flow.google.com"])
    runtime.start()
    try:
        # make the session unhealthy by going HUMAN_REQUIRED via registry
        runtime._registry.update_state("sess_test_01", BrowserSessionState.HUMAN_REQUIRED)
        with pytest.raises(BrowserSessionNotHealthyError):
            asyncio.run(
                runtime.execute(
                    BrowserOperation.OPEN_URL, target="https://flow.google.com/projects"
                )
            )
    finally:
        asyncio.run(runtime.stop())


def test_runtime_cancel_records_cancelled_evidence(tmp_path):
    runtime, process = _runtime(
        tmp_path, process=FakeProcess(delay_open_seconds=1.0)
    )

    async def run_with_cancel():
        runtime.start()
        task = asyncio.create_task(
            runtime.execute(
                BrowserOperation.OPEN_URL,
                target="https://flow.google.com/projects",
            )
        )
        # Deterministic: wait until the fake has *started* the `open` command
        # (i.e. the action is genuinely in flight), then cancel. The fake
        # blocks inside ``open`` so the cancel must land mid-action.
        for _ in range(200):
            if any(
                len(cmd) >= 2 and cmd[-2] == "open"
                for cmd in process.calls
            ):
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        cancelled = [
            r
            for r in runtime._evidence.recent()
            if r.result_state == BrowserActionResultState.CANCELLED
        ]
        assert cancelled
        await runtime.stop()

    asyncio.run(run_with_cancel())


def test_runtime_reattach_preserves_session_registry(tmp_path):
    runtime, process = _runtime(tmp_path)
    runtime.start()
    meta = runtime._registry.get("sess_test_01")
    assert meta is not None and meta.state == BrowserSessionState.READY
    asyncio.run(runtime.stop())
    # registry survives close
    registry = BrowserSessionRegistry(f"{tmp_path}/artifacts/browser_sessions", clock=time.time)
    assert registry.get("sess_test_01") is not None
    # reattach
    runtime2, process2 = _runtime(tmp_path)
    asyncio.run(runtime2.reattach())
    assert runtime2._registry.get("sess_test_01").state == BrowserSessionState.READY
    asyncio.run(runtime2.stop())


def test_runtime_timeout_raises_bounded_error(tmp_path):
    process = FakeProcess()
    process.raise_timeout = True
    runtime, _ = _runtime(tmp_path, process=process, action_timeout_seconds=0.5)
    runtime.start()
    try:
        with pytest.raises((BrowserActionTimeoutError, BrowserRuntimeError)):
            asyncio.run(
                runtime.execute(
                    BrowserOperation.OPEN_URL, target="https://flow.google.com/projects"
                )
            )
    finally:
        asyncio.run(runtime.stop())
