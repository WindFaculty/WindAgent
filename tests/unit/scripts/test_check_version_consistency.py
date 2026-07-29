from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace

from scripts import check_version_consistency as version_check


def test_canonical_import_failure_is_fatal(monkeypatch, tmp_path: Path):
    checker = version_check.VersionChecker(tmp_path)
    monkeypatch.setattr(
        version_check,
        "_CANONICAL_IMPORT_ERROR",
        "ModuleNotFoundError: injected",
    )

    assert checker.check_canonical_version_import() is False
    assert checker.errors
    assert checker.results["canonical_version_source"] == "fallback_metadata"


def test_worker_import_failure_is_fatal(monkeypatch, tmp_path: Path):
    checker = version_check.VersionChecker(tmp_path)
    real_import = builtins.__import__

    def fail_worker_import(name, *args, **kwargs):
        if name == "windagent_worker":
            raise ModuleNotFoundError("injected")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_worker_import)

    assert checker.check_worker_version() is False
    assert any("not importable" in error for error in checker.errors)


def test_cli_nonzero_exit_is_fatal(monkeypatch, tmp_path: Path):
    checker = version_check.VersionChecker(tmp_path)
    monkeypatch.setattr(
        version_check.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=7,
            stdout=version_check.PRODUCT_VERSION,
            stderr="injected",
        ),
    )

    assert checker.check_cli_version_command() is False
    assert checker.results["cli_version_returncode"] == 7
    assert any("exit 7" in error for error in checker.errors)


def test_api_nonzero_exit_is_fatal(monkeypatch, tmp_path: Path):
    checker = version_check.VersionChecker(tmp_path)
    monkeypatch.setattr(
        version_check.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=9,
            stdout=version_check.PRODUCT_VERSION,
            stderr="injected",
        ),
    )

    assert checker.check_api_openapi_version() is False
    assert checker.results["api_openapi_returncode"] == 9
    assert any("exit 9" in error for error in checker.errors)


def test_hardcoded_product_version_is_fatal(tmp_path: Path):
    source = tmp_path / "service.py"
    source.write_text(
        f'VERSION = "{version_check.PRODUCT_VERSION}"\n',
        encoding="utf-8",
    )
    checker = version_check.VersionChecker(tmp_path)

    assert checker.check_hardcoded_versions() is False
    assert any("hardcoded product version" in error for error in checker.errors)
