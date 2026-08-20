"""
Phase 7 version authority tests.

Validates that a single canonical product version is enforced across code,
package metadata, CLI, API, and worker runtime.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _checker(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_version_consistency.py"), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result.returncode, result.stdout, result.stderr


def test_canonical_version_constants_are_distinct():
    from windagent_core.version import (
        PRODUCT_VERSION,
        ARCHITECTURE_GENERATION,
        API_VERSION,
        PROVIDER_PROTOCOL_VERSION,
        ARTIFACT_PROTOCOL_VERSION,
    )

    assert PRODUCT_VERSION == "0.3.0"
    assert ARCHITECTURE_GENERATION == "v3"
    assert API_VERSION == "v3"
    assert PROVIDER_PROTOCOL_VERSION == "1.0.0"
    assert ARTIFACT_PROTOCOL_VERSION == "1.0.0"
    # Protocol versions must never be confused with the product version.
    assert API_VERSION != PRODUCT_VERSION
    assert PROVIDER_PROTOCOL_VERSION != PRODUCT_VERSION
    assert ARTIFACT_PROTOCOL_VERSION != PRODUCT_VERSION


def test_version_info_dictionary_has_expected_keys():
    from windagent_core.version import get_version_info

    info = get_version_info()
    assert set(info.keys()) == {
        "product_version",
        "architecture_generation",
        "api_version",
        "provider_protocol_version",
        "artifact_protocol_version",
    }


def test_checker_passes_from_repository_root():
    code, stdout, _ = _checker([])
    assert code == 0, stdout
    assert "VERSION CONSISTENCY CHECK: PASSED" in stdout


def test_checker_passes_from_subdirectory():
    code, stdout, _ = _checker(["--root", str(ROOT)])
    assert code == 0, stdout


def test_checker_fails_for_invalid_root():
    code, stdout, stderr = _checker(["--root", "D:/nonexistent_phase7_check"])
    assert code == 2, f"stdout={stdout}\nstderr={stderr}"
    assert "No pyproject.toml found" in (stdout + stderr)


def test_checker_fails_on_injected_version_mismatch(tmp_path: Path, monkeypatch):
    # Copy a minimal view of the repo root pyproject so we can mutate it safely.
    repo_copy = tmp_path / "repo"
    repo_copy.mkdir()
    (repo_copy / "pyproject.toml").write_text(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Mirror workspace member discovery minimally.
    (repo_copy / "core").mkdir()
    (repo_copy / "core" / "pyproject.toml").write_text(
        '[project]\nname = "windagent-core"\nversion = "0.99.0"\n',
        encoding="utf-8",
    )
    (repo_copy / "core" / "windagent_core").mkdir()
    (repo_copy / "core" / "windagent_core" / "version.py").write_text(
        'PRODUCT_VERSION = "0.3.0"\nARCHITECTURE_GENERATION = "v3"\n'
        'API_VERSION = "v3"\nPROVIDER_PROTOCOL_VERSION = "1.0.0"\n'
        'ARTIFACT_PROTOCOL_VERSION = "1.0.0"\n',
        encoding="utf-8",
    )

    code, stdout, _ = _checker(["--root", str(repo_copy)])
    assert code == 1, stdout
    assert "windagent-core version 0.99.0 != canonical product_version 0.3.0" in stdout


def test_cli_version_outputs_product_version():
    result = subprocess.run(
        [sys.executable, "-m", "windagent_cli", "--version", "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    from windagent_core.version import PRODUCT_VERSION
    assert PRODUCT_VERSION in result.stdout


def test_api_openapi_version_matches_product():
    from windagent_api.main import app
    from windagent_core.version import PRODUCT_VERSION
    assert app.version == PRODUCT_VERSION


def test_worker_module_version_matches_product():
    import windagent_worker
    from windagent_core.version import PRODUCT_VERSION
    assert windagent_worker.__version__ == PRODUCT_VERSION
