"""Phase 10 - Continuity Ledger canonical isolation tests (plan 03 §4, §17).

Proves the continuity ledger layer (`intelligence/windagent_intelligence/video/continuity/`)
meets the Phase 10 architecture rules:
- no upstream import / sys.path mutation / subprocess (clean-room, plan §4);
- provider-neutral: imports only `windagent_core` + `windagent_intelligence`;
  never imports `windagent_tools` / `windagent_providers` / browser modules;
- the continuity layer is fully deterministic (no model port required);
- core domain objects (ContinuityLedger / ContinuityLedgerEntry /
  ContinuityLedgerValidator / HumanContinuityOverride) live in core and stay
  intelligence/tools-neutral;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTINUITY_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "continuity"
CORE_CONTINUITY = ROOT / "core" / "windagent_core" / "domain" / "video_production" / "continuity.py"

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_intelligence")


def _continuity_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(CONTINUITY_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_continuity_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _continuity_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"continuity launches/imports upstream: {hits}"


def test_continuity_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _continuity_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"continuity imports forbidden deps: {offenders}"


def test_continuity_has_no_model_port_dependency():
    """Phase 10 ledger building is deterministic; the layer must not call a provider."""
    for rel, text in _continuity_py_files():
        assert "PreproductionModelPort" not in text, f"{rel} should not require a model port"
        assert "model_port" not in text, f"{rel} should not hold a model port"


def test_core_continuity_models_are_tools_neutral():
    text = CORE_CONTINUITY.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_intelligence" not in text
    assert "windagent_providers" not in text


def test_core_exports_continuity_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "ContinuityLedger",
        "ContinuityLedgerEntry",
        "ContinuityIssue",
        "ContinuityLedgerValidator",
        "HumanContinuityOverride",
        "compute_ledger_hash",
        "ContinuityFieldState",
        "ContinuityChange",
        "ContinuityAssertion",
        "ContinuityDiff",
        "ContinuityFieldSource",
        "ContinuityIssueCode",
    ):
        assert hasattr(vp, name), f"core missing export {name}"
    import windagent_core as core

    assert hasattr(core, "ContinuityLedger")
    assert hasattr(core, "ContinuityLedgerValidator")


def test_intelligence_exports_continuity_service():
    import windagent_intelligence.video as video

    for name in ("ContinuityLedgerService", "ContinuityLedgerReceipt"):
        assert hasattr(video, name), f"intelligence missing export {name}"


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
