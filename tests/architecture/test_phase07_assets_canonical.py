"""Phase 7 - Media asset pipeline canonical isolation tests (plan 02 §19-§23).

Proves the asset pipeline (`tools/windagent_tools/media_assets/`) and the
core lifecycle state machine (`windagent_core.domain.video_production.
asset_lifecycle`) meet plan 02 §20 / §21 requirements:
- the pipeline never imports or launches the quarantined upstream and never
  mutates `sys.path`;
- `tools` only depends on `windagent_core` (per architecture scaffold_v2:
  tools.allowed_dependencies = ["windagent_core"]);
- `core` remains provider/tools-neutral — the state machine lives in core
  and must not import `windagent_tools`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "tools" / "windagent_tools" / "media_assets"
CORE_LIFECYCLE = ROOT / "core" / "windagent_core" / "domain" / "video_production" / "asset_lifecycle.py"

# Real launch/import mechanisms that would execute upstream code or poison
# sys.path. These are forbidden inside the canonical packages.
UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
]

# Per architecture scaffold_v2, tools.allowed_dependencies = ["windagent_core"].
FORBIDDEN_TOOLS_DEP_ROOTS = (
    "windagent_intelligence",
    "windagent_providers",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
)
ALLOWED_TOOLS_DEP_ROOTS = ("windagent_core", "windagent_tools")


def _assets_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(ASSETS_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_asset_pipeline_never_launches_or_imports_upstream():
    """No upstream import / sys.path mutation / subprocess in the pipeline."""
    hits = []
    for rel, text in _assets_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"asset pipeline launches/imports upstream: {hits}"


def test_asset_pipeline_dependency_roots_are_canonical():
    """tools/media_assets imports only windagent_core + windagent_tools."""
    offenders = []
    for rel, text in _assets_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_TOOLS_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"asset pipeline imports forbidden deps: {offenders}"


def test_core_state_machine_is_tools_neutral():
    """asset_lifecycle.py (core) must not import windagent_tools."""
    text = CORE_LIFECYCLE.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text, "core lifecycle must be tools-neutral"
    assert "windagent_intelligence" not in text, "core lifecycle must not import intelligence"


def test_core_exports_asset_lifecycle():
    """The domain package re-exports the lifecycle state machine."""
    import windagent_core.domain.video_production as vp

    assert hasattr(vp, "AssetLifecycleState")
    assert hasattr(vp, "AssetStateMachine")


def test_real_repo_architecture_stays_clean():
    """The real workspace architecture check reports zero violations."""
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
