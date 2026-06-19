"""Tests for ``services.agent_s3_health``.

The health module is a thin aggregator so the suite mostly exercises
the dataclass -> dict shape and the summary builder.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.agent_s3_adapter import MockAgentS3Adapter
from services.agent_s3_config import (
    AgentS3Config,
    AgentS3ConfigStatus,
    load_agent_s3_config,
    status_from_config,
)
from services.agent_s3_health import (
    build_status,
    health_summary,
    status_to_dict,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("WINDAGENT_AGENT_S3_"):
            monkeypatch.delenv(key, raising=False)
    yield


def _make_config(**overrides) -> AgentS3Config:
    return AgentS3Config(
        enabled=overrides.get("enabled", False),
        source=overrides.get("source", "package"),
        external_path=Path(__file__),
        provider="openai",
        model="gpt-5",
        model_url="",
        model_api_key="",
        ground_provider="huggingface",
        ground_model="ui-tars",
        ground_url="",
        ground_api_key="",
        enable_local_env=False,
        external_checkout_root=(
            Path(overrides["external_checkout_root"])
            if overrides.get("external_checkout_root") is not None
            else None
        ),
        notes=(),
    )


# ---------- build_status ----------

def test_build_status_disabled_no_adapter():
    cfg = _make_config(enabled=False)
    st = build_status(cfg, None)
    assert st.mode == "disabled"
    assert st.enabled is False
    assert st.last_error is None
    assert st.extra["adapter_initialised"] is False
    assert st.extra["last_actions"] == []


def test_build_status_records_adapter_last_error():
    cfg = _make_config(enabled=False)
    a = MockAgentS3Adapter(cfg)
    # Manually inject a synthetic last_error.
    a._state.last_error = "boom"  # type: ignore[attr-defined]
    st = build_status(cfg, a)
    assert st.last_error == "boom"


def test_build_status_records_adapter_actions():
    cfg = _make_config(enabled=False)
    a = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(1, 2)"], info={}
    )
    # last_actions is populated by ``propose`` -- simulate that.
    a._state.last_actions = ["pyautogui.click(1, 2)"]  # type: ignore[attr-defined]
    st = build_status(cfg, a)
    assert st.extra["last_actions"] == ["pyautogui.click(1, 2)"]


# ---------- status_to_dict ----------

def test_status_to_dict_shape():
    cfg = _make_config(enabled=False)
    st = build_status(cfg, None)
    d = status_to_dict(st)
    assert d["mode"] == "disabled"
    assert d["enabled"] is False
    assert "package_available" in d
    assert "external_repo_available" in d
    assert "config_missing" in d
    assert "last_error" in d
    assert "config" in d
    assert "provider" in d["config"]
    assert "model" in d["config"]
    assert "enable_local_env" in d["config"]


def test_status_to_dict_surfaces_missing_config():
    cfg = load_agent_s3_config()
    # Force enabled=True with no provider/model so missing is non-empty.
    import dataclasses
    cfg2 = dataclasses.replace(cfg, enabled=True)
    st = build_status(cfg2, None)
    d = status_to_dict(st)
    assert d["enabled"] is True
    assert len(d["config_missing"]) > 0


# ---------- health_summary ----------

def test_health_summary_keys():
    cfg = _make_config(enabled=False)
    st = build_status(cfg, None)
    summary = health_summary(st)
    assert "agent_s3" in summary
    block = summary["agent_s3"]
    assert block["mode"] == "disabled"
    assert block["enabled"] is False
    # ``package_available`` reflects the current environment: it could be
    # True or False depending on whether ``gui-agents`` is installed in
    # the test venv. We only assert that the field exists + is a bool.
    assert isinstance(block["package_available"], bool)
    assert block["config_missing_count"] == 0


def test_health_summary_reports_missing_count():
    cfg = load_agent_s3_config()
    import dataclasses
    cfg2 = dataclasses.replace(cfg, enabled=True, provider="", model="")
    st = build_status(cfg2, None)
    summary = health_summary(st)
    assert summary["agent_s3"]["config_missing_count"] > 0


# ---------- End-to-end with FastAPI ----------

def test_agent_s3_health_endpoint_disabled(client):
    """GET /agent-s3/health works even when integration is off."""
    resp = client.get("/agent-s3/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "disabled"
    assert body["enabled"] is False


def test_root_health_includes_agent_s3_block(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "agent_s3" in body
    assert body["agent_s3"]["mode"] == "disabled"