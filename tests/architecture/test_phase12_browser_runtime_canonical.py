"""Phase 12 — Browser runtime foundation canonical isolation tests
(plan 04 §5, §8).

Proves the Phase 12 browser runtime (`tools/windagent_tools/browser/runtime.py`,
`action_policy.py`, `session.py`, `evidence_capture.py`, `healthcheck.py`)
meets the Phase 12 architecture rules:
- extends the existing `tools/windagent_tools/browser/` boundary — no parallel
  runtime package is created (plan 04 §5);
- tools-layer only: imports `windagent_tools` + `windagent_core`; never imports
  `windagent_providers`, `windagent_intelligence` Flow adapters or a Flow
  provider (no production Flow dependency, gate §10);
- the runtime never launches a browser inside the policy/evidence/health/session
  modules (deterministic offline classification);
- typed operations only — no raw model-generated browser commands;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BROWSER_DIR = ROOT / "tools" / "windagent_tools" / "browser"

PHASE12_FILES = (
    "action_policy.py",
    "session.py",
    "evidence_capture.py",
    "healthcheck.py",
    "runtime.py",
)

FORBIDDEN_LAUNCH_PATTERNS = [
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_intelligence",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
    "google_flow",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_tools")


def _phase12_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_phase12_runtime_modules_exist_in_existing_boundary():
    """Plan 04 §5: extend the existing browser package, no parallel runtime."""
    for name in PHASE12_FILES:
        assert (BROWSER_DIR / name).exists(), f"missing {name}"
    # no parallel package created
    assert not (ROOT / "tools" / "windagent_tools" / "browser_runtime").exists()
    assert not (ROOT / "tools" / "windagent_tools" / "flow_browser").exists()


def test_phase12_policy_modules_never_launch_a_browser():
    for name in PHASE12_FILES:
        text = _phase12_text(BROWSER_DIR / name)
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            assert pattern.search(text) is None, (
                f"{name} must not launch processes or mutate sys.path"
            )


def test_phase12_dependency_roots_are_tools_and_core_only():
    offenders = []
    for name in PHASE12_FILES:
        text = _phase12_text(BROWSER_DIR / name)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{name}: {stripped}")
    assert offenders == [], f"phase12 imports forbidden deps: {offenders}"


def test_phase12_runtime_uses_typed_operations_only():
    """Plan 04 §8.4: no raw browser command strings are accepted."""
    text = _phase12_text(BROWSER_DIR / "runtime.py")
    # the runtime only dispatches on BrowserOperation enum members
    assert "BrowserOperation.OPEN_URL" in text
    assert "BrowserOperation.SNAPSHOT" in text
    assert "BrowserOperation.CLICK" in text
    # deny-class operations live in the policy matrix, not the dispatch table
    policy_text = _phase12_text(BROWSER_DIR / "action_policy.py")
    assert "EVAL" in policy_text
    # no model-generated command injection surface
    assert "model_generated" not in text.replace("model_generated_command", "")


def test_phase12_deny_operations_never_executed():
    """Arbitrary eval / cookie export / filesystem reads are denied by policy."""
    text = _phase12_text(BROWSER_DIR / "action_policy.py")
    assert "EVAL" in text
    assert "COOKIE_EXPORT" in text
    assert "FILESYSTEM_READ" in text
    # the runtime must not have an execution branch for deny-class operations
    runtime_text = _phase12_text(BROWSER_DIR / "runtime.py")
    assert "operation == BrowserOperation.EVAL" not in runtime_text
    assert "operation == BrowserOperation.COOKIE_EXPORT" not in runtime_text


def test_phase12_evidence_never_stores_raw_content():
    """Plan 04 §8.5: evidence stores hashes, never raw screenshots/pages."""
    text = _phase12_text(BROWSER_DIR / "evidence_capture.py")
    assert "redacted_screenshot_hash" in text
    assert "snapshot_hash" in text
    assert "sha256" in text
    # no raw content fields in the evidence record
    assert '"screenshot"' not in text.replace("redacted_screenshot_hash", "")


def test_phase12_health_is_offline_classification():
    """Plan 04 §8.5: health check classifies from observable signals."""
    text = _phase12_text(BROWSER_DIR / "healthcheck.py")
    assert "process_alive" in text
    assert "browser_reachable" in text
    assert "current_domain_allowed" in text
    assert "profile_lock_valid" in text
    assert "HUMAN_REQUIRED" in text
    # classification never opens a browser
    assert "client.open" not in text


def test_phase12_exported_symbols():
    import windagent_tools.browser as browser

    for name in (
        "BrowserRuntime",
        "BrowserActionPolicy",
        "BrowserOperation",
        "BrowserProfileLock",
        "BrowserSessionRegistry",
        "BrowserSessionMetadata",
        "BrowserSessionState",
        "BrowserEvidenceRecorder",
        "BrowserActionEvidence",
        "BrowserActionResultState",
        "BrowserHealthCheck",
        "BrowserHealthReport",
        "BrowserHealthStatus",
        "BrowserActionDeniedError",
        "BrowserRuntimeError",
        "BrowserSessionNotHealthyError",
    ):
        assert hasattr(browser, name), f"browser package missing export {name}"


def test_phase12_tools_package_re_exports_runtime():
    import windagent_tools as tools

    assert hasattr(tools, "BrowserRuntime")
    assert hasattr(tools, "BrowserActionPolicy")
    assert hasattr(tools, "BrowserHealthCheck")


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
