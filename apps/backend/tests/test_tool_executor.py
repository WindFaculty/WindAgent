"""Unit tests for ToolExecutor with MockGuiAdapter.

No real GUI / pyautogui / subprocess calls happen. We verify:
  - validation errors become status="failed" with INVALID_TOOL_OR_PARAMS
  - successful calls record adapter invocation + emit events + write DB
  - failed calls record error payload + emit failed event + write DB
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from db.models import ExecutionEventORM, ToolCallORM
from services.event_bus import drain
from services.gui_adapter import MockGuiAdapter
from services.tool_executor import ToolExecutor
from services.tool_registry import TOOL_REGISTRY


# ---------- Helpers ----------

def _make_executor(bus, db, *, fail_on: str | None = None) -> tuple[ToolExecutor, MockGuiAdapter]:
    gui = MockGuiAdapter(fail_on=fail_on)
    return ToolExecutor(event_bus=bus, db=db, gui=gui), gui


# ---------- Validation failures ----------

@pytest.mark.asyncio
async def test_unknown_tool_name_returns_failed_status(event_bus, db):
    exec, _ = _make_executor(event_bus, db)
    sid, step = uuid.uuid4(), uuid.uuid4()
    q = await event_bus.subscribe(str(sid))

    result = await exec.execute(sid, step, "no_such_tool", {})

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_TOOL_OR_PARAMS"
    # We still emit a tool_call_finished event for failed validations.
    events = await drain(q)
    names = [e.event for e in events]
    # No tool_call_started for validation failure (it never ran).
    assert "tool_call_started" not in names
    assert "tool_call_finished" in names


@pytest.mark.asyncio
async def test_bad_params_returns_failed_status(event_bus, db):
    exec, _ = _make_executor(event_bus, db)
    sid, step = uuid.uuid4(), uuid.uuid4()
    q = await event_bus.subscribe(str(sid))

    result = await exec.execute(sid, step, "open_app", {"app": "photoshop"})

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_TOOL_OR_PARAMS"


# ---------- Successful execution ----------

@pytest.mark.asyncio
async def test_open_app_invokes_adapter_and_emits_events(event_bus, db):
    exec, gui = _make_executor(event_bus, db)
    sid, step = uuid.uuid4(), uuid.uuid4()
    q = await event_bus.subscribe(str(sid))

    result = await exec.execute(sid, step, "open_app", {"app": "notepad"})

    assert result["status"] == "success"
    assert result["output"]["app"] == "notepad"
    assert result["output"]["pid"] > 0

    # Adapter was called exactly once with right name.
    assert len(gui.calls) == 1
    assert gui.calls[0]["tool"] == "open_app"
    assert gui.calls[0]["app"] == "notepad"

    # Events emitted: started + finished.
    events = await drain(q)
    names = [e.event for e in events]
    assert names == ["tool_call_started", "tool_call_finished"]
    assert events[0].data["input"] == {"app": "notepad"}
    assert events[1].data["status"] == "success"


@pytest.mark.asyncio
async def test_type_text_uses_paste_method_for_vietnamese(event_bus, db):
    exec, gui = _make_executor(event_bus, db)
    sid = uuid.uuid4()

    result = await exec.execute(
        sid, None, "type_text",
        {"text": "Xin chào", "method": "paste"},
    )

    assert result["status"] == "success"
    call = next(c for c in gui.calls if c["tool"] == "type_text")
    assert call["method"] == "paste"
    assert call["text"] == "Xin chào"


@pytest.mark.asyncio
async def test_wait_does_not_block(event_bus, db):
    """The mock adapter records but does not actually sleep."""
    import time as _t

    exec, _ = _make_executor(event_bus, db)
    sid = uuid.uuid4()

    start = _t.perf_counter()
    result = await exec.execute(sid, None, "wait", {"seconds": 5.0})
    elapsed = _t.perf_counter() - start

    assert result["status"] == "success"
    assert elapsed < 0.5  # mock doesn't sleep 5s


@pytest.mark.asyncio
async def test_screenshot_returns_path(event_bus, db):
    exec, _ = _make_executor(event_bus, db)
    sid = uuid.uuid4()

    result = await exec.execute(
        sid, None, "screenshot", {"name": "test-shot"}
    )

    assert result["status"] == "success"
    assert "path" in result["output"]
    assert str(sid) in result["output"]["path"]


# ---------- DB persistence ----------

@pytest.mark.asyncio
async def test_successful_call_writes_tool_call_row(event_bus, db):
    exec, _ = _make_executor(event_bus, db)
    sid, step = uuid.uuid4(), uuid.uuid4()
    await exec.execute(sid, step, "open_app", {"app": "calc"})

    async with db.session() as s:
        rows = (await s.execute(
            select(ToolCallORM).where(ToolCallORM.session_id == str(sid))
        )).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "open_app"
        assert row.status == "success"
        assert row.step_id == str(step)
        out = json.loads(row.output_json)
        assert out["app"] == "calc"


@pytest.mark.asyncio
async def test_failed_call_writes_error_row(event_bus, db):
    exec, _ = _make_executor(event_bus, db, fail_on="hotkey")
    sid = uuid.uuid4()

    result = await exec.execute(
        sid, None, "hotkey", {"keys": ["ctrl", "c"]}
    )

    assert result["status"] == "failed"

    async with db.session() as s:
        rows = (await s.execute(
            select(ToolCallORM).where(ToolCallORM.session_id == str(sid))
        )).scalars().all()
        # We expect 2 rows: the failed-call row + a traceback sibling row.
        assert len(rows) == 2
        statuses = {r.status for r in rows}
        assert "failed" in statuses
        assert "traceback" in statuses


@pytest.mark.asyncio
async def test_event_bus_receives_tool_call_finished_for_failure(event_bus, db):
    exec, _ = _make_executor(event_bus, db, fail_on="open_app")
    sid = uuid.uuid4()
    q = await event_bus.subscribe(str(sid))

    result = await exec.execute(sid, None, "open_app", {"app": "notepad"})

    assert result["status"] == "failed"
    events = await drain(q)
    finished = next(e for e in events if e.event == "tool_call_finished")
    assert finished.data["status"] == "failed"
    assert finished.data["error"]["type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_event_bus_receives_tool_call_started_via_execution_events(event_bus, db):
    """Events should also be mirrored to execution_events by the hook."""
    exec, _ = _make_executor(event_bus, db)
    sid = uuid.uuid4()
    await exec.execute(sid, None, "open_app", {"app": "explorer"})

    async with db.session() as s:
        rows = (await s.execute(
            select(ExecutionEventORM).where(ExecutionEventORM.session_id == str(sid))
        )).scalars().all()
        types = {r.event_type for r in rows}
        assert "tool_call_started" in types
        assert "tool_call_finished" in types
