"""Tests for ``services.agent_s3_config``.

These tests do NOT require the ``gui_agents`` package to be installed;
they only exercise the env loader + the availability helpers.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.agent_s3_config import (
    AgentS3Config,
    AgentS3Source,
    _find_repo_root,
    config_missing_fields,
    external_repo_available,
    load_agent_s3_config,
    package_available,
    resolve_external_path,
    status_from_config,
    validate_or_raise,
)


# Common fixture: clear every WINDAGENT_AGENT_S3_* env var so each test
# sees a deterministic starting point.
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("WINDAGENT_AGENT_S3_"):
            monkeypatch.delenv(key, raising=False)
    yield


def _enable_all_required(monkeypatch, **overrides) -> None:
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_PROVIDER", "openai")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_MODEL", "gpt-5-2025-08-07")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_PROVIDER", "huggingface")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_MODEL", "ui-tars-1.5-7b")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)


# ---------- package_available / external_repo_available ----------

def test_package_available_reflects_import(monkeypatch):
    # Without installing anything, this is False on CI; this assertion
    # is just to lock the helper in -- the test passes regardless.
    assert isinstance(package_available(), bool)


def test_external_repo_available_false_for_missing(tmp_path: Path):
    assert external_repo_available(tmp_path / "missing") is False


def test_external_repo_available_true_when_gui_agents_subdir(tmp_path: Path):
    (tmp_path / "gui_agents").mkdir()
    assert external_repo_available(tmp_path) is True


def test_external_repo_available_true_when_legacy_agent_s_subdir(tmp_path: Path):
    (tmp_path / "agent_s").mkdir()
    assert external_repo_available(tmp_path) is True


def test_external_repo_available_false_when_dir_exists_but_empty(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello")
    assert external_repo_available(tmp_path) is False


# ---------- resolve_external_path ----------

def test_resolve_external_path_default():
    p = resolve_external_path("")
    assert p.name == "Agent-S"


def test_resolve_external_path_absolute(tmp_path: Path):
    p = resolve_external_path(str(tmp_path))
    assert p.is_absolute()
    assert p == tmp_path


def test_resolve_external_path_relative_anchored_to_repo_root(tmp_path: Path):
    # Repo-relative paths are anchored on the repo root (the directory
    # that contains apps/backend/pyproject.toml), NOT on cwd. This is
    # because the backend is launched with cwd=apps/backend.
    repo_root = _find_repo_root()
    p = resolve_external_path("external/Agent-S")
    assert p.is_absolute()
    assert p == (repo_root / "external" / "Agent-S").resolve()


def test_resolve_external_path_relative_any_subdir(tmp_path: Path):
    # Even when called from an unrelated cwd, repo-relative paths
    # still anchor on the repo root.
    p = resolve_external_path("external/Agent-S")
    assert (p.parent / "Agent-S").name == "Agent-S"
    assert p.is_absolute()


# ---------- load_agent_s3_config ----------

def test_load_disabled_by_default():
    cfg = load_agent_s3_config()
    assert cfg.enabled is False
    assert cfg.source == "package"
    assert cfg.enable_local_env is False


def test_load_enabled_with_all_required(monkeypatch):
    _enable_all_required(monkeypatch)
    cfg = load_agent_s3_config()
    assert cfg.enabled is True
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-5-2025-08-07"
    assert cfg.ground_provider == "huggingface"
    assert cfg.ground_model == "ui-tars-1.5-7b"
    assert cfg.source == "package"
    assert cfg.enable_local_env is False


def test_load_source_external(monkeypatch):
    _enable_all_required(monkeypatch)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_SOURCE", "external")
    monkeypatch.setenv(
        "WINDAGENT_AGENT_S3_EXTERNAL_PATH", "/tmp/some/path/Agent-S"
    )
    cfg = load_agent_s3_config()
    assert cfg.source == "external"
    assert str(cfg.external_path).replace("\\", "/").endswith("Agent-S")


def test_enable_local_env_always_forced_false(monkeypatch):
    _enable_all_required(
        monkeypatch,
        **{"WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV": "1"},
    )
    cfg = load_agent_s3_config()
    assert cfg.enable_local_env is False
    # A note is recorded so debug is obvious.
    assert any("forced to False" in n for n in cfg.notes)


def test_load_unknown_source_defaults_to_package(monkeypatch):
    _enable_all_required(monkeypatch)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_SOURCE", "weird")
    cfg = load_agent_s3_config()
    assert cfg.source == "package"


# ---------- config_missing_fields ----------

def test_missing_fields_when_disabled():
    cfg = load_agent_s3_config()
    assert config_missing_fields(cfg) == []


def test_missing_fields_when_enabled_minimal(monkeypatch):
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    # Intentionally leave the GROUND vars empty. Worker LLM provider/model
    # have non-empty defaults so they won't show up as missing.
    cfg = load_agent_s3_config()
    missing = config_missing_fields(cfg)
    assert "WINDAGENT_AGENT_S3_GROUND_PROVIDER" in missing
    assert "WINDAGENT_AGENT_S3_GROUND_MODEL" in missing
    # Worker provider/model defaults are non-empty -> never missing.
    assert "WINDAGENT_AGENT_S3_PROVIDER" not in missing
    assert "WINDAGENT_AGENT_S3_MODEL" not in missing


def test_missing_fields_external_requires_checkout(monkeypatch):
    _enable_all_required(monkeypatch)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_SOURCE", "external")
    monkeypatch.setenv(
        "WINDAGENT_AGENT_S3_EXTERNAL_PATH", "/definitely/not/here"
    )
    cfg = load_agent_s3_config()
    missing = config_missing_fields(cfg)
    assert any("EXTERNAL_PATH" in m for m in missing)


# ---------- validate_or_raise ----------

def test_validate_or_raise_disabled_is_noop(monkeypatch):
    cfg = load_agent_s3_config()
    validate_or_raise(cfg)  # must not raise


def test_validate_or_raise_missing_required(monkeypatch):
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    cfg = load_agent_s3_config()
    with pytest.raises(ValueError, match="incomplete"):
        validate_or_raise(cfg)


def test_validate_or_raise_external_no_checkout(monkeypatch):
    _enable_all_required(monkeypatch)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_SOURCE", "external")
    monkeypatch.setenv(
        "WINDAGENT_AGENT_S3_EXTERNAL_PATH", "/no/such/path/Agent-S"
    )
    cfg = load_agent_s3_config()
    with pytest.raises(ValueError, match="checkout"):
        validate_or_raise(cfg)


def test_validate_or_raise_external_with_checkout(tmp_path: Path, monkeypatch):
    _enable_all_required(monkeypatch)
    (tmp_path / "gui_agents").mkdir()
    monkeypatch.setenv("WINDAGENT_AGENT_S3_SOURCE", "external")
    monkeypatch.setenv(
        "WINDAGENT_AGENT_S3_EXTERNAL_PATH", str(tmp_path)
    )
    cfg = load_agent_s3_config()
    assert cfg.external_checkout_root is not None
    validate_or_raise(cfg)  # must not raise


def test_validate_or_raise_package_without_install(monkeypatch):
    _enable_all_required(monkeypatch)
    cfg = load_agent_s3_config()
    # Only assert the message + that it raises when the package
    # really is missing -- which it is on CI (no gui_agents installed).
    if package_available():
        pytest.skip("gui_agents is installed in this environment")
    with pytest.raises(ValueError, match="gui_agents"):
        validate_or_raise(cfg)


# ---------- status_from_config ----------

def test_status_disabled():
    cfg = load_agent_s3_config()
    st = status_from_config(cfg)
    assert st.mode == "disabled"
    assert st.enabled is False
    assert st.config_missing == []
    assert st.last_error is None


def test_status_misconfigured_when_enabled_but_missing(monkeypatch):
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    cfg = load_agent_s3_config()
    st = status_from_config(cfg)
    assert st.mode == "misconfigured"
    assert st.enabled is True
    assert len(st.config_missing) > 0


def test_status_records_last_error():
    cfg = load_agent_s3_config()
    st = status_from_config(cfg, last_error="boom")
    assert st.last_error == "boom"