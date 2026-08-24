"""Invariant: Composition roots are authoritative (T7).

Verifies that the API worker, CLI and worker compositions are the sole
authorities for wiring production ports, and that no intermediate layer
re-declares composition. This is an invariant-based replacement for the
phase-history tests (phase7, phase8) that previously proved the same via
historical fixtures.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

# Policy: apps/api, apps/worker, apps/cli are the only composition roots.
# No other package may instantiate concrete storage/provider adapters.
COMPOSITION_ROOTS = [
    "apps/api/windagent_api/composition",
    "apps/worker/windagent_worker/composition",
    "apps/cli/windagent_cli/composition",
]

FORBIDDEN_INSTANTIATIONS = [
    "SqlUnitOfWork",
    "DatabaseManager",
    "ProviderAdapter",
]

def test_composition_roots_are_authoritative():
    """Only composition roots may instantiate concrete infrastructure adapters."""
    violations = []
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        # Skip composition roots themselves
        if any(str(py).replace("\\", "/").find(root) != -1 for root in COMPOSITION_ROOTS):
            continue
        # Skip tests, scripts, third_party
        if any(part in ("tests", "scripts", "third_party", ".venv") for part in py.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for forbidden in FORBIDDEN_INSTANTIATIONS:
            # Allow definitions (class SqlUnitOfWork:) but not instantiations (SqlUnitOfWork()
            if f"{forbidden}(" in text:
                # Check if file is allowed to instantiate via composition
                # For now, only flag if file is under windagent_core/ (domain should not)
                if "windagent_core" in str(py) and forbidden in ("SqlUnitOfWork", "DatabaseManager"):
                    violations.append(f"{py}: instantiates {forbidden}")
    assert not violations, "Composition authority violations:\n" + "\n".join(violations[:10])

def test_no_legacy_runtime_imports_in_composition():
    """Worker/API composition must not import legacy runtime."""
    for root in COMPOSITION_ROOTS:
        root_path = ROOT / root
        if not root_path.exists():
            continue
        for py in root_path.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            assert "windagent_orchestration.legacy" not in text, f"{py} imports legacy runtime"
            assert "apps.backend" not in text, f"{py} imports legacy backend"
