"""Tests for shared repository root locator (Phase 3)."""
import subprocess
import sys
from pathlib import Path

import pytest

from windagent_core.config.repository_root import find_repository_root, is_repository_root

ROOT = Path(__file__).resolve().parents[3]


def test_finds_root_from_repo_root():
    assert find_repository_root(ROOT) == ROOT.resolve()


def test_finds_root_from_subdirectory():
    assert find_repository_root(ROOT / "apps" / "cli") == ROOT.resolve()


def test_finds_root_from_deep_subdirectory():
    assert find_repository_root(ROOT / "apps" / "api" / "windagent_api") == ROOT.resolve()


def test_is_repository_root_true():
    assert is_repository_root(ROOT)


def test_is_repository_root_false_for_apps_cli():
    assert not is_repository_root(ROOT / "apps" / "cli")


def test_invalid_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_repository_root(tmp_path)


def test_architecture_check_passes_from_subdirectory():
    result = subprocess.run(
        [sys.executable, "-m", "windagent_cli", "architecture-check", "--json"],
        cwd=ROOT / "apps" / "cli",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    import json
    data = json.loads(result.stdout)
    assert data["verdict"] == "PASS"
    assert data["all_required_checks_executed"] is True
    assert Path(data["repository_root"]) == ROOT.resolve()


def test_architecture_check_fails_closed_outside_repo(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "windagent_cli", "architecture-check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "Repository root not found" in (result.stdout + result.stderr)
