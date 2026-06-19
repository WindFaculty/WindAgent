"""Unit tests for ``services.agent_s3_step_executor.AgentS3StepExecutor``.

Covers the full failure matrix from the Phase 12 brief:

  * AGENT_S3_DISABLED           (config.enabled=False)
  * AGENT_S3_ADAPTER_NOT_READY  (adapter=None)
  * AGENT_S3_UNAVAILABLE        (adapter.is_available()=False)
  * AGENT_S3_PROPOSE_FAILED     (adapter.propose raises)
  * AGENT_S3_UNSAFE_ACTION      (raw action matches deny pattern)
  * AGENT_S3_UNSUPPORTED_ACTION (no whitelist match)
  * MAPPED_TOOL_NOT_WHITELISTED (defence-in-depth)
  * MAPPED_TOOL_INVALID_PARAMS  (translated params fail Pydantic)
  * MAPPED_TOOL_EXECUTION_FAILED (inner run_mapped_tool raises)
  * success path (dry_run=True)
  * success path (dry_run=False, mapped click_xy)

The mock adapter + mock GUI + fake run_mapped_tool are injected; no
real Agent-S3 SDK or PyAutoGUI is required.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from services.agent_s3_action_translator import (
    RejectedAction,
    TranslatedAction,
)
from services.agent_s3_adapter import AgentS3Adapter, AgentS3Proposal, MockAgentS3Adapter
from services.agent_s3_config import (
    AgentS3Config,
    AgentS3ConfigStatus,
    load_agent_s3_config,
)
from services.agent_s3_step_executor import (
    AGENT_S3_MAPPED_TOOL_ALLOWLIST,
    AgentS3StepExecutor,
    AgentS3StepResult,
)
from services.event_bus import EventBus
from services.tool_registry import AgentS3StepParams


# ---------- Fixtures ----------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("WINDAGENT_AGENT_S3_"):
            monkeypatch.delenv(key, raising=False)
    yield


def _make_config(**overrides) -> AgentS3Config:
    base = dict(
        enabled=True,
        source="package",
        external_path=Path("/tmp/external"),
        provider="openai",
        model="gpt-5",
        model_url="",
        model_api_key="",
        ground_provider="huggingface",
        ground_model="ui-tars",
        ground_url="",
        ground_api_key="",
        enable_local_env=False,
    )
    base.update(overrides)
    return AgentS3Config(**base)


def _make_params(**overrides) -> AgentS3StepParams:
    base = dict(
        instruction="Click the OK button if visible",
        screenshot=False,
        dry_run=False,
        max_retries=0,
        require_permission=True,
        timeout_ms=30_000,
    )
    base.update(overrides)
    return AgentS3StepParams(**base)


class _FakeGui:
    """Minimal stand-in for GuiAdapter that just records the call."""

    def __init__(self, raise_on_screenshot: Optional[Exception] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._raise = raise_on_screenshot

    def screenshot(self, *, name: str, out_dir: Path) -> Dict[str, Any]:
        if self._raise is not None:
            raise self._raise
        path = out_dir / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        self.calls.append({"name": name, "out_dir": str(out_dir), "path": str(path)})
        return {"path": str(path), "name": name}


class _FakeRunMappedTool:
    """Records every call so tests can assert what was executed."""

    def __init__(
        self,
        *,
        raise_on_call: Optional[Exception] = None,
        return_value: Optional[Dict[str, Any]] = None,
        record: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._raise = raise_on_call
        self._return = return_value or {"ok": True}
        self.calls = record if record is not None else []

    def __call__(
        self, tool_name: str, params: Dict[str, Any], session_id
    ) -> Dict[str, Any]:
        self.calls.append(
            {"tool_name": tool_name, "params": dict(params), "session_id": str(session_id)}
        )
        if self._raise is not None:
            raise self._raise
        return dict(self._return)


def _make_orchestrator(
    *,
    config: AgentS3Config,
    adapter: Optional[AgentS3Adapter],
    run_mapped_tool=None,
    gui: Optional[_FakeGui] = None,
    artifacts_root: Optional[Path] = None,
) -> AgentS3StepExecutor:
    bus = EventBus()
    orch = AgentS3StepExecutor(
        config=config,
        adapter=adapter,
        event_bus=bus,
        artifacts_root=artifacts_root or Path("/tmp/windagent-test-artifacts"),
        run_mapped_tool=run_mapped_tool or _FakeRunMappedTool(),
    )
    if gui is not None:
        orch.bind_gui_for_screenshot(gui)
    return orch


# ---------- AGENT_S3_DISABLED ----------

@pytest.mark.asyncio
async def test_disabled_returns_agent_s3_disabled():
    cfg = _make_config(enabled=False)
    orch = _make_orchestrator(config=cfg, adapter=None)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_DISABLED"
    assert result.proposal is None
    assert result.translation is None
    assert result.mapped is None


# ---------- AGENT_S3_ADAPTER_NOT_READY ----------

@pytest.mark.asyncio
async def test_adapter_none_returns_adapter_not_ready():
    cfg = _make_config(enabled=True)
    orch = _make_orchestrator(config=cfg, adapter=None)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_ADAPTER_NOT_READY"


# ---------- AGENT_S3_UNAVAILABLE ----------

@pytest.mark.asyncio
async def test_adapter_unavailable_returns_unavailable():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(cfg, available=False)
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNAVAILABLE"


# ---------- AGENT_S3_PROPOSE_FAILED ----------

@pytest.mark.asyncio
async def test_propose_raises_returns_propose_failed():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, raise_on_call=RuntimeError("upstream blew up")
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_PROPOSE_FAILED"
    assert "upstream blew up" in (result.error_message or "")


# ---------- AGENT_S3_UNSAFE_ACTION (deny pattern) ----------

@pytest.mark.asyncio
async def test_unsafe_action_os_system_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=['os.system("calc")']
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"
    assert result.translation is not None
    assert result.translation.rejected
    assert result.translation.rejected[0].reason.startswith("denied:")


@pytest.mark.asyncio
async def test_unsafe_action_subprocess_run_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["subprocess.run(['ls'])"]
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"


@pytest.mark.asyncio
async def test_unsafe_action_open_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(cfg, actions=['open("/etc/passwd")'])
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"


@pytest.mark.asyncio
async def test_unsafe_action_exec_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=['exec("malicious code")']
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"


@pytest.mark.asyncio
async def test_unsafe_action_eval_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=['eval("1+1")']
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"


@pytest.mark.asyncio
async def test_unsafe_action_import_returns_unsafe_action():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(cfg, actions=["import os"])
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSAFE_ACTION"


# ---------- AGENT_S3_UNSUPPORTED_ACTION (no whitelist match) ----------

@pytest.mark.asyncio
async def test_unsupported_action_my_custom_call_returns_unsupported():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["my_custom_function(123, 456)"]
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "AGENT_S3_UNSUPPORTED_ACTION"
    assert result.translation is not None
    assert not result.translation.accepted


# ---------- MAPPED_TOOL_NOT_WHITELISTED (defence-in-depth) ----------

@pytest.mark.asyncio
async def test_defence_in_depth_rejects_outside_allowlist(monkeypatch):
    """Simulate a hypothetical translator regression that maps to a
    tool the orchestrator allow-list forbids."""
    cfg = _make_config(enabled=True)
    # Use a recognised pyautogui pattern that maps to click_xy; then
    # monkey-patch the orchestrator's allow-list to NOT include click_xy.
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)
    monkeypatch.setattr(
        "services.agent_s3_step_executor.AGENT_S3_MAPPED_TOOL_ALLOWLIST",
        frozenset({"hotkey"}),  # exclude click_xy on purpose
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "MAPPED_TOOL_NOT_WHITELISTED"
    assert result.mapped is not None
    assert result.mapped.tool_name == "click_xy"


# ---------- MAPPED_TOOL_INVALID_PARAMS ----------

@pytest.mark.asyncio
async def test_invalid_params_after_translate_returns_invalid_params(monkeypatch):
    """Simulate LLM hallucinating bad params for a recognised pattern.

    The translator regex accepts ``pyautogui.click(x, y)`` with
    integers; we monkey-patch the click_xy validator to fail so the
    orchestrator's defence-in-depth layer catches it.
    """
    from services import tool_registry as tr
    from pydantic import ValidationError

    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    orch = _make_orchestrator(config=cfg, adapter=adapter)

    original_validate = tr.validate_params

    def boom(name, params):
        if name == "click_xy":
            raise ValidationError.from_exception_data(
                "ClickXyParams",
                [{"type": "value_error", "loc": ("x",), "input": params.get("x"),
                  "ctx": {"error": "boom"}, "msg": "x must be int"}],
            )
        return original_validate(name, params)

    monkeypatch.setattr(tr, "validate_params", boom)
    # The orchestrator imported the symbol; patch it on the
    # orchestrator's own import too.
    import services.agent_s3_step_executor as a3
    monkeypatch.setattr(a3, "validate_params", boom)

    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "MAPPED_TOOL_INVALID_PARAMS"
    assert result.mapped is not None
    assert result.mapped.tool_name == "click_xy"


# ---------- MAPPED_TOOL_EXECUTION_FAILED ----------

@pytest.mark.asyncio
async def test_inner_tool_execution_failed():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    fake = _FakeRunMappedTool(raise_on_call=RuntimeError("pyautogui blew up"))
    orch = _make_orchestrator(
        config=cfg, adapter=adapter, run_mapped_tool=fake
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(),
    )
    assert result.status == "failed"
    assert result.error_code == "MAPPED_TOOL_EXECUTION_FAILED"
    assert "pyautogui blew up" in (result.error_message or "")
    # The inner call still happened before the raise.
    assert len(fake.calls) == 1
    assert fake.calls[0]["tool_name"] == "click_xy"
    assert fake.calls[0]["params"] == {"x": 100, "y": 200, "button": "left"}


# ---------- Success path: dry_run=True ----------

@pytest.mark.asyncio
async def test_dry_run_does_not_call_inner_tool():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    fake = _FakeRunMappedTool(return_value={"would_have_called": True})
    orch = _make_orchestrator(
        config=cfg, adapter=adapter, run_mapped_tool=fake
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=False),
    )
    assert result.status == "success"
    assert result.dry_run is True
    assert result.mapped is not None
    assert result.mapped.tool_name == "click_xy"
    assert result.mapped_execution_output == {"dry_run": True}
    # Critical safety contract: inner tool NOT invoked.
    assert fake.calls == [], (
        f"dry_run must not call run_mapped_tool; saw {fake.calls!r}"
    )
    # Proposal + translation present so audit trail has full evidence.
    assert result.proposal is not None
    assert result.translation is not None
    assert len(result.translation.accepted) == 1


# ---------- Success path: dry_run=False, mapped click_xy ----------

@pytest.mark.asyncio
async def test_full_flow_click_xy_executes():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(123, 456)"]
    )
    fake = _FakeRunMappedTool(return_value={"clicked_at": {"x": 123, "y": 456}})
    orch = _make_orchestrator(
        config=cfg, adapter=adapter, run_mapped_tool=fake
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=False, screenshot=False),
    )
    assert result.status == "success"
    assert result.dry_run is False
    assert result.mapped is not None
    assert result.mapped.tool_name == "click_xy"
    assert result.mapped_execution_output == {
        "clicked_at": {"x": 123, "y": 456}
    }
    assert len(fake.calls) == 1
    assert fake.calls[0]["params"] == {"x": 123, "y": 456, "button": "left"}


# ---------- Success path: type_text ----------

@pytest.mark.asyncio
async def test_full_flow_type_text_executes():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=['pyautogui.typewrite("hello")']
    )
    fake = _FakeRunMappedTool()
    orch = _make_orchestrator(
        config=cfg, adapter=adapter, run_mapped_tool=fake
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=False, screenshot=False),
    )
    assert result.status == "success"
    assert result.mapped.tool_name == "type_text"
    assert result.mapped.params["text"] == "hello"
    assert fake.calls[0]["params"]["text"] == "hello"


# ---------- event emission ----------

@pytest.mark.asyncio
async def test_emits_agent_s3_action_proposed_on_success():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    bus = EventBus()
    sid = uuid.uuid4()
    q = await bus.subscribe(str(sid))
    orch = AgentS3StepExecutor(
        config=cfg,
        adapter=adapter,
        event_bus=bus,
        artifacts_root=Path("/tmp"),
        run_mapped_tool=_FakeRunMappedTool(),
    )
    await orch.execute(
        session_id=sid, step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=False),
    )
    # Drain the subscriber queue.
    drained = []
    while not q.empty():
        drained.append(q.get_nowait())
    proposed = [
        e for e in drained
        if getattr(e, "event", None) == "agent_s3_action_proposed"
    ]
    assert len(proposed) == 1, f"expected 1 proposal event; got {len(proposed)}"
    assert proposed[0].data["safety_status"] == "accepted"
    assert proposed[0].data["translated_tool"] == "click_xy"
    assert proposed[0].data["dry_run"] is True
    await bus.unsubscribe(str(sid), q)


# ---------- Audit / output dict hygiene ----------

@pytest.mark.asyncio
async def test_output_dict_redacts_api_keys_in_proposal_info():
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg,
        actions=["pyautogui.click(100, 200)"],
        info={"api_key": "sk-tes...3456", "model": "gpt-5", "apiKey": "sk-tes...3456"},
    )
    orch = _make_orchestrator(
        config=cfg, adapter=adapter,
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=False),
    )
    out = result.to_output_dict()
    raw = __import__("json").dumps(out)
    # Never echo api_key-style fields from upstream info.
    assert "sk-tes...3456" not in raw
    assert "sk-tes...3456" not in raw
    # Safe fields still present.
    assert out["proposal"]["info"]["model"] == "gpt-5"


@pytest.mark.asyncio
async def test_output_dict_truncates_long_raw_actions():
    cfg = _make_config(enabled=True)
    huge = "pyautogui.click(1, 1)  # " + ("x" * 1000)
    adapter = MockAgentS3Adapter(
        cfg, actions=[huge, "pyautogui.click(2, 2)"]
    )
    orch = _make_orchestrator(
        config=cfg, adapter=adapter,
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=False),
    )
    out = result.to_output_dict()
    # The first raw action should be truncated.
    assert any(
        "<truncated>" in a for a in out["proposal"]["raw_actions"]
    )


# ---------- Screenshot handling ----------

@pytest.mark.asyncio
async def test_screenshot_path_recorded_when_screenshot_true(tmp_path):
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    gui = _FakeGui()
    orch = _make_orchestrator(
        config=cfg,
        adapter=adapter,
        gui=gui,
        artifacts_root=tmp_path,
        run_mapped_tool=_FakeRunMappedTool(),
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=True),
    )
    assert result.screenshot_path is not None
    assert "shot-" in (result.screenshot_path or "")
    assert len(gui.calls) == 1


@pytest.mark.asyncio
async def test_screenshot_failure_does_not_abort_step(tmp_path):
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg, actions=["pyautogui.click(100, 200)"]
    )
    gui = _FakeGui(raise_on_screenshot=RuntimeError("display gone"))
    orch = _make_orchestrator(
        config=cfg,
        adapter=adapter,
        gui=gui,
        artifacts_root=tmp_path,
        run_mapped_tool=_FakeRunMappedTool(),
    )
    result = await orch.execute(
        session_id=uuid.uuid4(), step_id=uuid.uuid4(),
        params=_make_params(dry_run=True, screenshot=True),
    )
    assert result.status == "success"
    assert result.screenshot_path is None
    # Still produced a proposal (with empty observation).
    assert result.proposal is not None


# ---------- Allowlist sanity ----------

def test_allowlist_matches_brief():
    """Pin the explicit allow-list from the Phase 12 brief."""
    expected = {
        "click_xy", "type_text", "hotkey", "press_key",
        "scroll", "wait", "screenshot",
    }
    assert AGENT_S3_MAPPED_TOOL_ALLOWLIST == expected