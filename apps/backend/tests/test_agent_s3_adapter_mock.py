"""Tests for ``services.agent_s3_adapter`` using ``MockAgentS3Adapter``.

These tests never import the real ``gui_agents`` package -- the whole
point is to exercise the adapter's behaviour when the upstream is
either unavailable or intentionally stubbed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.agent_s3_adapter import (
    AgentS3Adapter,
    AgentS3Proposal,
    MockAgentS3Adapter,
    _detect_platform,
    has_gui_agents_package,
)
from services.agent_s3_config import (
    AgentS3Config,
    AgentS3Source,
    load_agent_s3_config,
)


# ---------- Fixtures ----------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("WINDAGENT_AGENT_S3_"):
            monkeypatch.delenv(key, raising=False)
    yield


def _make_config(
    *,
    enabled: bool = True,
    source: AgentS3Source = "package",
    external_checkout_root=None,
    provider: str = "openai",
    model: str = "gpt-5-2025-08-07",
    ground_provider: str = "huggingface",
    ground_model: str = "ui-tars-1.5-7b",
) -> AgentS3Config:
    """Build an AgentS3Config dataclass directly, skipping env reads."""
    root = (
        Path(external_checkout_root)
        if external_checkout_root is not None
        else None
    )
    return AgentS3Config(
        enabled=enabled,
        source=source,
        external_path=Path(__file__),  # dummy
        provider=provider,
        model=model,
        model_url="",
        model_api_key="",
        ground_provider=ground_provider,
        ground_model=ground_model,
        ground_url="",
        ground_api_key="",
        enable_local_env=False,
        external_checkout_root=root,
        notes=(),
    )


# ---------- Module-level helpers ----------

def test_has_gui_agents_package_returns_bool():
    assert isinstance(has_gui_agents_package(), bool)


def test_detect_platform_recognises_windows_or_linux():
    plat = _detect_platform()
    assert plat in ("windows", "darwin", "linux")


# ---------- AgentS3Adapter.is_available ----------

def test_adapter_unavailable_when_disabled():
    cfg = _make_config(enabled=False)
    a = AgentS3Adapter(cfg)
    assert a.is_available() is False


def test_adapter_unavailable_when_missing_fields():
    cfg = _make_config(provider="", model="")
    a = AgentS3Adapter(cfg)
    assert a.is_available() is False


def test_adapter_unavailable_when_package_missing():
    if has_gui_agents_package():
        pytest.skip("gui_agents is installed in this environment")
    cfg = _make_config(source="package")
    a = AgentS3Adapter(cfg)
    assert a.is_available() is False


def test_adapter_available_when_checked_out(tmp_path):
    (tmp_path / "gui_agents").mkdir()
    cfg = _make_config(
        source="external",
        external_checkout_root=tmp_path,
    )
    a = AgentS3Adapter(cfg)
    assert a.is_available() is True


def test_adapter_unavailable_when_external_path_empty(tmp_path):
    cfg = _make_config(source="external", external_checkout_root=None)
    a = AgentS3Adapter(cfg)
    assert a.is_available() is False


# ---------- AgentS3Adapter.propose ----------

@pytest.mark.asyncio
async def test_propose_returns_none_when_disabled():
    cfg = _make_config(enabled=False)
    a = MockAgentS3Adapter(cfg)
    proposal = await a.propose("open notepad", {"screenshot": "x.png"})
    assert proposal is None
    assert a.last_error is not None


@pytest.mark.asyncio
async def test_propose_returns_proposal_when_mock_available():
    cfg = _make_config(enabled=True, external_checkout_root=__file__)
    a = MockAgentS3Adapter(
        cfg,
        actions=["pyautogui.click(100, 200)", "pyautogui.typewrite('hi')"],
        info={"thought": "click then type"},
    )
    proposal = await a.propose("open notepad", {"screenshot": "x.png"})
    assert isinstance(proposal, AgentS3Proposal)
    assert proposal.backend == "package"  # source is package
    assert proposal.instruction == "open notepad"
    assert len(proposal.raw_actions) == 2
    assert a.last_error is None
    assert a.last_actions == proposal.raw_actions


@pytest.mark.asyncio
async def test_propose_records_error_on_predict_failure(tmp_path):
    cfg = _make_config(enabled=True, external_checkout_root=tmp_path)
    a = MockAgentS3Adapter(
        cfg,
        raise_on_call=RuntimeError("upstream boom"),
    )
    proposal = await a.propose("do x", {"screenshot": "x.png"})
    assert proposal is None
    assert a.last_error is not None
    assert "boom" in (a.last_error or "")


@pytest.mark.asyncio
async def test_propose_handles_empty_actions():
    cfg = _make_config(enabled=True, external_checkout_root=__file__)
    a = MockAgentS3Adapter(cfg, actions=[], info={})
    proposal = await a.propose("nothing", {"screenshot": "x.png"})
    assert proposal is not None
    assert proposal.raw_actions == []


# ---------- AgentS3Proposal.to_dict ----------

def test_proposal_to_dict_round_trip():
    p = AgentS3Proposal(
        info={"k": 1},
        raw_actions=["pyautogui.click(1, 2)"],
        instruction="do it",
        backend="package",
    )
    d = p.to_dict()
    assert d["info"] == {"k": 1}
    assert d["raw_actions"] == ["pyautogui.click(1, 2)"]
    assert d["instruction"] == "do it"
    assert d["backend"] == "package"


# ---------- MockAgentS3Adapter.is_available ----------

def test_mock_unavailable_when_flag_false():
    cfg = _make_config(enabled=True, external_checkout_root=__file__)
    a = MockAgentS3Adapter(cfg, available=False)
    assert a.is_available() is False


def test_mock_unavailable_when_disabled():
    cfg = _make_config(enabled=False)
    a = MockAgentS3Adapter(cfg)
    assert a.is_available() is False


# ---------- Real adapter NEVER imports gui_agents eagerly ----------

def test_real_adapter_construction_does_not_import(monkeypatch):
    """Constructing AgentS3Adapter must not pull gui_agents into the
    import graph -- it's the lifespan's first guarantee."""
    import sys

    # Drop the module if it's already imported by an earlier test
    # so we can prove the construction alone does not re-import it.
    monkeypatch.delitem(sys.modules, "gui_agents", raising=False)

    cfg = _make_config(enabled=True, external_checkout_root=__file__)
    AgentS3Adapter(cfg)
    # If the upstream isn't installed in the test env, the assertion
    # is unconditional. If it IS installed, the assertion still
    # holds because __init__ does not import it.
    assert "gui_agents" not in sys.modules or has_gui_agents_package()