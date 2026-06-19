"""HTTP integration tests for the tools router."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from db.models import ExecutionEventORM, ToolCallORM


def test_list_tools_returns_mvp_whitelisted(client):
    resp = client.get("/tools")
    assert resp.status_code == 200
    names = resp.json()
    # Phase 8 added click_target (vision-grounded click); 10 tools
    # total in the MVP whitelist.
    assert set(names) == {
        "open_app", "open_url", "type_text", "hotkey", "press_key",
        "click_xy", "click_target", "scroll", "screenshot", "wait",
    }


def test_run_tool_unknown_session_returns_404(client):
    resp = client.post(
        "/sessions/00000000-0000-4000-8000-000000000999/tools/open_app",
        json={"params": {"app": "notepad"}},
    )
    assert resp.status_code == 404


def test_run_tool_unknown_tool_returns_failed(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/no_such_tool",
        json={"params": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "INVALID_TOOL_OR_PARAMS"


def test_run_tool_bad_params_returns_failed(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/open_app",
        json={"params": {"app": "photoshop"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "INVALID_TOOL_OR_PARAMS"


def test_run_open_app_success(client, gui):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/open_app",
        json={"params": {"app": "notepad"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"]["app"] == "notepad"
    assert body["duration_ms"] >= 0
    # Adapter was called.
    assert any(c["tool"] == "open_app" for c in gui.calls)


def test_run_type_text_persists_vietnamese(client, db):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/tools/type_text",
        json={"params": {"text": "Xin chào bạn", "method": "paste"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # DB row created.
    import asyncio
    async def _check():
        async with db.session() as s:
            rows = (await s.execute(
                select(ToolCallORM).where(ToolCallORM.session_id == sid)
            )).scalars().all()
            assert len(rows) == 1
            inp = json.loads(rows[0].input_json)
            assert inp["text"] == "Xin chào bạn"

    asyncio.run(_check())


def test_run_workflow_executes_all_steps(client, gui):
    """End-to-end: send message -> run workflow -> see all steps executed."""
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello"},
    )

    resp = client.post(f"/sessions/{sid}/workflow/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["step_count"] == 2
    assert len(body["results"]) == 2
    for r in body["results"]:
        assert r["status"] == "success"
    tools_called = [c["tool"] for c in gui.calls]
    assert "open_app" in tools_called
    assert "type_text" in tools_called


def test_run_workflow_without_workflow_returns_404(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(f"/sessions/{sid}/workflow/run")
    assert resp.status_code == 404


def test_run_workflow_emits_full_event_sequence(client):
    """Phase 5: send_message auto-starts the runner which emits
    tool_call_started/finished for each step.

    The manual /workflow/run endpoint is not called here because the
    runner is already executing the workflow in the background.
    """
    import time
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hi"},
    )
    # Let the runner finish (MockGuiAdapter is instant).
    time.sleep(0.3)

    # Inspect execution_events DB for the session.
    import asyncio
    from db.models import ExecutionEventORM

    async def _check():
        from db.database import Database
        from sqlalchemy import select
        import os
        d = Database(os.environ["WINDAGENT_DB_URL"])
        try:
            async with d.session() as s:
                rows = (await s.execute(
                    select(ExecutionEventORM)
                    .where(ExecutionEventORM.session_id == sid)
                    .order_by(ExecutionEventORM.created_at)
                )).scalars().all()
                return [r.event_type for r in rows]
        finally:
            await d.dispose()

    types = asyncio.run(_check())
    # message_received + planning_started + planning_finished + workflow_created
    # + step_started (x2) + step_completed (x2)
    # + tool_call_started (x2) + tool_call_finished (x2)
    for expected in (
        "message_received", "planning_started", "planning_finished",
        "workflow_created", "tool_call_started", "tool_call_finished",
        "step_started", "step_completed", "session_finished",
    ):
        assert expected in types, f"missing event {expected} in {types}"
    # Two tool calls -> 2 started + 2 finished.
    assert types.count("tool_call_started") == 2
    assert types.count("tool_call_finished") == 2
    # Two steps -> 2 started + 2 completed.
    assert types.count("step_started") == 2
    assert types.count("step_completed") == 2
    # One session_finished with final_status=completed.
    assert types.count("session_finished") == 1
