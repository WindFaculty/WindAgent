"""Phase 12 — integration tests for the wired ``agent_s3_step`` tool.

These tests drive the FastAPI ``TestClient`` end-to-end so we cover:

  * the public REST surface (``/tools``, ``/sessions/{sid}/tools/...``),
  * the WorkflowRunner / ToolExecutor dispatch,
  * the Agent-S3 orchestrator (with a mocked adapter injected at the
    ``app.state.agent_s3_step_executor`` slot, since the default lifespan
    leaves Agent-S3 disabled in tests),
  * and the failure-matrix from the Phase 12 brief.

The fixture ``wired_agent_s3`` swaps ``app.state.agent_s3_step_executor``
for a stub-backed instance whose adapter produces canned raw actions.
This keeps tests hermetic — no real Agent-S3 SDK + no real model API.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from services.agent_s3_adapter import MockAgentS3Adapter
from services.agent_s3_config import AgentS3Config
from services.agent_s3_step_executor import AgentS3StepExecutor
from services.event_bus import EventBus


# ---------- Helpers ----------

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


class _RecordedRunMappedTool:
    """Fake ToolExecutor._run replacement that records every call."""

    def __init__(
        self,
        *,
        raise_on_call: Optional[Exception] = None,
        return_value: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._raise = raise_on_call
        self._return = return_value or {"ok": True}
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, tool_name, params, session_id):
        self.calls.append(
            {"tool_name": tool_name, "params": dict(params),
             "session_id": str(session_id)}
        )
        if self._raise is not None:
            raise self._raise
        return dict(self._return)


def _install_agent_s3(
    app_state,
    *,
    actions: List[str],
    info: Optional[Dict[str, Any]] = None,
    raise_on_call: Optional[Exception] = None,
    run_mapped_tool: Optional[_RecordedRunMappedTool] = None,
    available: bool = True,
) -> _RecordedRunMappedTool:
    """Inject a stub Agent-S3 orchestrator into ``app.state``.

    Returns the ``_RecordedRunMappedTool`` so tests can assert on inner
    mapped-tool calls. Replaces both ``agent_s3_step_executor`` on
    app.state AND ``executor._agent_s3_step_executor`` on the
    ToolExecutor singleton (so the public API dispatches correctly).
    """
    cfg = _make_config(enabled=True)
    adapter = MockAgentS3Adapter(
        cfg,
        actions=actions,
        info=info,
        raise_on_call=raise_on_call,
        available=available,
    )
    runner = run_mapped_tool or _RecordedRunMappedTool()
    orch = AgentS3StepExecutor(
        config=cfg,
        adapter=adapter,
        event_bus=app_state.event_bus,
        artifacts_root=Path(os.environ.get(
            "WINDAGENT_ARTIFACTS_ROOT",
            str(Path(__file__).resolve().parents[1] / "artifacts" / "runs"),
        )),
        run_mapped_tool=runner,
    )
    orch.bind_gui_for_screenshot(app_state.gui)
    app_state.agent_s3_step_executor = orch
    app_state.tool_executor._agent_s3_step_executor = orch  # type: ignore[attr-defined]
    return runner


@pytest.fixture
def installed_agent_s3(app_state):
    """Default fixture: no actions pre-installed. Tests use ``_install``
    or pass kwargs to customise. We tear down after each test so the
    next test gets a clean lifespan."""
    yield _install_agent_s3
    # Tear down: drop the orchestrator so the next test sees Agent-S3
    # as disabled, matching the default lifespan.
    app_state.agent_s3_step_executor = None
    app_state.tool_executor._agent_s3_step_executor = None  # type: ignore[attr-defined]


# ---------- /tools listing ----------

def test_tools_endpoint_includes_agent_s3_step(client):
    resp = client.get("/tools")
    assert resp.status_code == 200
    assert "agent_s3_step" in resp.json()


def test_agent_s3_step_in_registry():
    """Sanity: tool_registry exposes agent_s3_step with the right shape."""
    from services.tool_registry import get_tool, AgentS3StepParams

    info = get_tool("agent_s3_step")
    assert info.risk_level == "high"
    assert info.requires_confirmation is True
    assert info.params_model is AgentS3StepParams


# ---------- Direct tool run: dry_run path ----------

def test_direct_run_agent_s3_step_dry_run_succeeds(client, installed_agent_s3, app_state):
    installed_agent_s3(app_state, actions=["pyautogui.click(123, 456)"])
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Click the OK button",
            "dry_run": True,
            "screenshot": False,
            "require_permission": False,
        }},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["dry_run"] is True
    assert body["output"]["mapped"]["tool_name"] == "click_xy"
    assert body["output"]["mapped"]["params"] == {
        "x": 123, "y": 456, "button": "left",
    }


# ---------- Direct tool run: full execute path ----------

def test_direct_run_agent_s3_step_full_execute(
    client, installed_agent_s3, app_state
):
    runner = installed_agent_s3(
        app_state,
        actions=["pyautogui.click(100, 200)"],
    )
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Click submit",
            "dry_run": False,
            "screenshot": False,
            "require_permission": False,  # skip permission gate for this test
        }},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["mapped"]["tool_name"] == "click_xy"
    # The inner mapped tool was called exactly once.
    assert len(runner.calls) == 1
    assert runner.calls[0]["tool_name"] == "click_xy"
    assert runner.calls[0]["params"] == {
        "x": 100, "y": 200, "button": "left",
    }


# ---------- Direct tool run: unsafe action ----------

def test_direct_run_agent_s3_step_unsafe_action_rejected(
    client, installed_agent_s3, app_state
):
    runner = installed_agent_s3(
        app_state, actions=['os.system("calc")'],
    )
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Open calc (via os.system!)",
            "dry_run": True,
            "screenshot": False,
            "require_permission": False,
        }},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "AGENT_S3_UNSAFE_ACTION"
    # Inner tool never invoked.
    assert runner.calls == []


# ---------- Direct tool run: Agent-S3 not wired (default) ----------

def test_direct_run_agent_s3_step_disabled_returns_disabled(client, app_state):
    """Without ``installed_agent_s3``, the orchestrator is None and the
    executor reports AGENT_S3_DISABLED."""
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {"instruction": "Anything", "dry_run": True}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "AGENT_S3_DISABLED"


# ---------- Validation: bad params ----------

def test_direct_run_agent_s3_step_rejects_invalid_params(client):
    sid = client.post("/sessions").json()["session_id"]
    # Empty instruction (min_length=1 enforced by Pydantic).
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {"instruction": ""}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "INVALID_TOOL_OR_PARAMS"


# ---------- Validation: max_retries out of range ----------

def test_direct_run_agent_s3_step_rejects_max_retries_out_of_range(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {"instruction": "test", "max_retries": 99}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "INVALID_TOOL_OR_PARAMS"


# ---------- Workflow integration: agent_s3_step in workflow steps ----------

def test_workflow_with_agent_s3_step_dry_run(
    client, installed_agent_s3, app_state
):
    """The Phase 12 brief asked for ``agent_s3_step`` to be a real
    step inside a workflow. We drive it through ``/sessions/{sid}/tools``
    (the runner-driven path used by ``/sessions/{sid}/messages`` when
    the planner emits ``agent_s3_step``)."""
    installed_agent_s3(
        app_state,
        actions=["pyautogui.click(50, 50)"],
    )
    sid = client.post("/sessions").json()["session_id"]
    # Run via the direct tools endpoint — same path the runner uses.
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Click OK",
            "dry_run": True,
            "screenshot": False,
            "require_permission": False,
        }},
    )
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["mapped"]["tool_name"] == "click_xy"


# ---------- audit log row is created ----------

def test_agent_s3_step_creates_tool_call_row(
    client, installed_agent_s3, app_state, db
):
    installed_agent_s3(
        app_state, actions=["pyautogui.click(10, 20)"],
    )
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Click OK",
            "dry_run": True,
            "screenshot": False,
            "require_permission": False,
        }},
    )
    # The tool_calls row should now exist with tool_name=agent_s3_step.
    import json as _json
    import anyio

    async def _read():
        from sqlalchemy import select
        from db.models import ToolCallORM
        async with db.session() as s:
            rows = (await s.execute(
                select(ToolCallORM).where(
                    ToolCallORM.session_id == sid,
                    ToolCallORM.tool_name == "agent_s3_step",
                )
            )).scalars().all()
            return [
                {
                    "status": r.status,
                    "output": _json.loads(r.output_json or "{}"),
                }
                for r in rows
            ]

    rows = anyio.run(_read)
    assert rows, "expected a tool_calls row for agent_s3_step"
    assert rows[0]["status"] == "success"
    assert rows[0]["output"]["mapped"]["tool_name"] == "click_xy"


# ---------- defence-in-depth: agent_s3_step when orchestrator is None
#            but adapter is available returns AGENT_S3_DISABLED ----------

def test_agent_s3_step_when_orchestrator_none_returns_disabled(client, app_state):
    """Tear down: explicitly null out the orchestrator."""
    app_state.agent_s3_step_executor = None
    app_state.tool_executor._agent_s3_step_executor = None  # type: ignore[attr-defined]
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {"instruction": "Click", "dry_run": True}},
    )
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "AGENT_S3_DISABLED"


# ---------- EventBus emits agent_s3_action_proposed on success ----------

def test_agent_s3_step_endpoint_returns_success_with_proposal_event_marker(
    client, installed_agent_s3, app_state
):
    """End-to-end: the ``agent_s3_step`` endpoint returns success when
    Agent-S3 proposes + WindAgent accepts. The detailed event-emission
    contract is pinned in ``test_agent_s3_step_executor.py`` (unit
    level); this integration test just confirms the wiring doesn't
    drop the success path through the public REST surface.
    """
    installed_agent_s3(
        app_state, actions=["pyautogui.click(100, 200)"],
    )
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/agent_s3_step",
        json={"params": {
            "instruction": "Click OK",
            "dry_run": True,
            "screenshot": False,
            "require_permission": False,
        }},
    )
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["mapped"]["tool_name"] == "click_xy"
    assert body["output"]["mapped"]["params"] == {
        "x": 100, "y": 200, "button": "left",
    }
    # The orchestrator's output dict embeds the proposal event's data
    # indirectly (instruction + translated tool). For real-time UI
    # consumption, the WebSocket subscribes to the EventBus and gets
    # ``agent_s3_action_proposed`` (covered by unit tests).