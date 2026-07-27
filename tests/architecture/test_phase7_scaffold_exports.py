"""
Regression tests for Phase 7 package public exports and scaffold convergence.

These tests protect the authoritative version contract and ensure scaffold
operations remain idempotent while preserving app-layer public APIs.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def scaffold_check_result():
    """Run the scaffold checker once per module."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scaffold_architecture_v2.py"), "--check"],
        capture_output=True,
        text=True,
    )
    return result


def test_scaffold_check_passes(scaffold_check_result):
    assert scaffold_check_result.returncode == 0, scaffold_check_result.stdout + scaffold_check_result.stderr
    assert "Scaffold Check Passed" in scaffold_check_result.stdout


def test_scaffold_create_is_idempotent():
    """Running --create twice must not produce any changes on the second run."""
    result1 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scaffold_architecture_v2.py"), "--create"],
        capture_output=True,
        text=True,
    )
    assert result1.returncode == 0, result1.stdout + result1.stderr

    result2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scaffold_architecture_v2.py"), "--create"],
        capture_output=True,
        text=True,
    )
    assert result2.returncode == 0, result2.stdout + result2.stderr
    assert "0 files updated" in result2.stdout, result2.stdout


def test_worker_public_exports():
    """Worker package must expose its durable lease and runner public API."""
    import windagent_worker

    assert hasattr(windagent_worker, "TaskLeaseManager")
    assert hasattr(windagent_worker, "DurableTaskLeaseManager")
    assert hasattr(windagent_worker, "TaskLease")
    assert hasattr(windagent_worker, "ProductionWorker")
    assert hasattr(windagent_worker, "WorkerRunner")
    assert "TaskLeaseManager" in windagent_worker.__all__
    assert "ProductionWorker" in windagent_worker.__all__


def test_worker_version_is_canonical():
    import windagent_worker
    import windagent_core.version

    assert windagent_worker.__version__ == windagent_core.version.PRODUCT_VERSION


def test_api_version_is_canonical():
    import windagent_api
    import windagent_core.version

    assert windagent_api.__version__ == windagent_core.version.PRODUCT_VERSION


def test_cli_version_is_canonical():
    import windagent_cli
    import windagent_core.version

    assert windagent_cli.__version__ == windagent_core.version.PRODUCT_VERSION


def test_core_version_is_canonical():
    import windagent_core
    import windagent_core.version

    assert windagent_core.__version__ == windagent_core.version.PRODUCT_VERSION


def test_missing_required_export_detected(tmp_path, monkeypatch):
    """Scaffold check must fail when a configured required export is absent."""
    from scripts import scaffold_architecture_v2 as scaffold

    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    fake_pkg = fake_root / "apps" / "worker" / "windagent_worker"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text(
        'from windagent_core.version import PRODUCT_VERSION\n__version__ = PRODUCT_VERSION\n',
        encoding="utf-8",
    )

    # Minimal config: one package with a required export that the init lacks.
    config = {
        "packages": {
            "worker": {
                "path": "apps/worker",
                "namespace": "windagent_worker",
                "description": "Worker",
                "public_exports": {
                    "required": {"ProductionWorker": "windagent_worker.runner"}
                },
            }
        }
    }
    monkeypatch.setattr(scaffold, "ROOT_DIR", fake_root)
    monkeypatch.setattr(scaffold, "load_config", lambda: config)

    current = (fake_pkg / "__init__.py").read_text(encoding="utf-8")
    ok = scaffold.scaffold_matches(
        fake_pkg / "__init__.py", current, "", config["packages"]["worker"]
    )
    assert not ok
