"""Phase 13 — Flow navigation canonical isolation tests (plan 04 §5, §13).

Proves the Phase 13 google_flow adapter
(`tools/windagent_tools/google_flow/`) meets the Phase 13 architecture rules:
- tools-layer: imports only `windagent_tools` + `windagent_core`; never
  imports `windagent_providers` / `windagent_intelligence` (plan 04 §5:
  `providers/` does not depend on `tools/google_flow`);
- no subprocess / sys.path mutation / dynamic import in the adapter
  (deterministic offline classification + navigation);
- typed operations only — the navigator never executes a raw browser command
  and never submits a generation (plan §13.3, §15);
- selector strategy is semantic-first (no CSS class / DOM index / coordinate
  as primary selectors, plan §13.4);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOOGLE_FLOW_DIR = ROOT / "tools" / "windagent_tools" / "google_flow"

FORBIDDEN_LAUNCH_PATTERNS = [
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_intelligence",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_tools")


def _google_flow_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(GOOGLE_FLOW_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase13_google_flow_exists_in_tools_boundary():
    assert GOOGLE_FLOW_DIR.is_dir()
    for name in (
        "state_machine.py",
        "navigation.py",
        "project_manager.py",
        "__init__.py",
    ):
        assert (GOOGLE_FLOW_DIR / name).exists(), f"missing {name}"
    assert (GOOGLE_FLOW_DIR / "selectors" / "catalog.py").exists()


def test_phase13_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _google_flow_py_files():
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase13 launches/imports upstream: {hits}"


def test_phase13_dependency_roots_are_tools_and_core_only():
    offenders = []
    for rel, text in _google_flow_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase13 imports forbidden deps: {offenders}"


def test_phase13_navigator_never_submits():
    """Plan 04 §15: navigation reaches SUBMIT_READY without submitting."""
    text = (GOOGLE_FLOW_DIR / "navigation.py").read_text(encoding="utf-8")
    # no submit operation in the navigator's action vocabulary
    assert "FlowUiAction(\"submit\"" not in text
    assert "operation=\"submit\"" not in text
    # submission is gated behind an explicit allow_submit flag
    assert "allow_submit" in text
    # the navigator does not call a provider port
    assert "MediaGenerationProviderPort" not in text


def test_phase13_typed_operations_only():
    """Plan 04 §13.3: typed bounded actions, never raw browser commands."""
    text = (GOOGLE_FLOW_DIR / "navigation.py").read_text(encoding="utf-8")
    assert "class FlowUiAction" in text
    assert "operation" in text  # typed operation name
    for raw in ("eval(", "exec(", "document.cookie", "click_xy"):
        assert raw not in text


def test_phase13_selector_strategy_semantic_first():
    """Plan 04 §13.4: no CSS class / DOM index / coordinate as primary."""
    catalog_text = (GOOGLE_FLOW_DIR / "selectors" / "catalog.py").read_text(
        encoding="utf-8"
    )
    assert "SelectorKind.ROLE" in catalog_text
    assert "SelectorKind.LABEL" in catalog_text
    assert "SelectorKind.TEXT" in catalog_text
    assert "SelectorKind.URL" in catalog_text
    assert "SelectorKind.REGION" in catalog_text
    assert "css_class" in catalog_text  # explicitly forbidden as primary
    assert "coordinate" in catalog_text


def test_phase13_state_machine_multi_signal():
    """Plan 04 §12: state is never inferred from a single selector."""
    text = (GOOGLE_FLOW_DIR / "state_machine.py").read_text(encoding="utf-8")
    assert "markers" in text
    assert "controls" in text
    assert "url" in text
    assert "classify" in text


def test_phase13_exports():
    import windagent_tools.google_flow as gf

    for name in (
        "FlowUiState",
        "FlowUiStateMachine",
        "FlowUiObservation",
        "FlowStateTransition",
        "FlowRetryClassification",
        "FlowNavigator",
        "FlowNavigationReceipt",
        "FlowNavigationDriftError",
        "FlowUiAction",
        "FlowUiPort",
        "FlowProjectManager",
        "FlowProjectMapping",
        "FlowProjectMappingStatus",
        "FlowProjectVerificationError",
        "FlowProjectMissingError",
        "SelectorCatalog",
        "SelectorEntry",
        "SelectorKind",
    ):
        assert hasattr(gf, name), f"google_flow missing export {name}"

    import windagent_tools as tools

    assert hasattr(tools, "FlowNavigator")
    assert hasattr(tools, "FlowProjectManager")
    assert hasattr(tools, "FlowUiStateMachine")
    assert hasattr(tools, "SelectorCatalog")


def test_phase13_never_imports_phase12_runtime_subprocess():
    """google_flow must not itself launch processes (the Phase 12 runtime
    owns process handling; google_flow acts through the typed UI port)."""
    for rel, text in _google_flow_py_files():
        assert "SubprocessAgentBrowserProcess" not in text, rel


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
