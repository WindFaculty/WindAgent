"""Phase 2 — SQLite persistence tests.

Verifies the four acceptance criteria from ban_ke_hoach.md §2.4:
  1. Tạo session -> DB có row.
  2. Gửi message -> DB có message.
  3. Workflow được tạo -> DB có workflow + steps.
  4. Event được stream và cũng được lưu vào DB.
Plus a restart-cycle test: data survives app restart.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from db.models import (
    ChatSessionORM,
    ExecutionEventORM,
    MessageORM,
    WorkflowORM,
    WorkflowStepORM,
)


# ---------- Helpers ----------

async def _reset_db_file(url: str) -> None:
    """Drop + recreate all tables in the test DB file."""
    from db.database import Database
    from db.models import Base

    db = Database(url)
    try:
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await db.dispose()


# ---------- 1. Session → DB row ----------

@pytest.mark.asyncio
async def test_create_session_writes_to_chat_sessions_table(client, app_state, db):
    sess = client.post("/sessions").json()
    sid = sess["session_id"]

    async with db.session() as s:
        row = await s.get(ChatSessionORM, sid)
        assert row is not None
        assert row.id == sid
        assert row.status == "idle"
        assert row.created_at is not None
        assert row.updated_at is not None


@pytest.mark.asyncio
async def test_update_status_writes_to_db(client, app_state, db):
    sid = client.post("/sessions").json()["session_id"]
    # Drive a message to flip status -> planning -> pending -> running -> completed
    client.post(f"/sessions/{sid}/messages", json={"content": "Mở Notepad và gõ Hi"})

    async with db.session() as s:
        row = await s.get(ChatSessionORM, sid)
        assert row is not None
        # Phase 5: runner auto-starts, so the row is whatever the runner
        # currently reports — but it MUST have moved away from "idle".
        assert row.status != "idle"
        assert row.status in {"planning", "pending", "running", "completed"}


# ---------- 2. Message → DB row ----------

@pytest.mark.asyncio
async def test_user_message_persisted(client, app_state, db):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello"},
    )
    body = resp.json()
    mid = body["message_id"]

    async with db.session() as s:
        msg = await s.get(MessageORM, mid)
        assert msg is not None
        assert msg.session_id == sid
        assert msg.sender == "user"
        assert msg.content == "Mở Notepad và gõ Hello"


# ---------- 3. Workflow + steps → DB rows ----------

@pytest.mark.asyncio
async def test_workflow_and_steps_persisted(client, app_state, db):
    sid = client.post("/sessions").json()["session_id"]
    body = client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello from local AI agent."},
    ).json()
    wf_id = body["workflow_id"]
    assert wf_id

    async with db.session() as s:
        wf = await s.get(WorkflowORM, wf_id)
        assert wf is not None
        assert wf.session_id == sid
        # Phase 5: runner auto-started and likely already marked the
        # workflow running/completed. Accept any post-creation status.
        assert wf.status in {"pending", "running", "completed"}

        step_rows = (await s.execute(
            select(WorkflowStepORM)
            .where(WorkflowStepORM.workflow_id == wf_id)
            .order_by(WorkflowStepORM.order_index)
        )).scalars().all()

        assert len(step_rows) == 2
        assert step_rows[0].tool_name == "open_app"
        assert step_rows[0].order_index == 1
        assert step_rows[1].tool_name == "type_text"
        assert step_rows[1].order_index == 2
        # params_json round-trips (parser strips trailing punctuation)
        import json as _json
        params = _json.loads(step_rows[1].params_json)
        assert params["text"].startswith("Hello from local AI agent")


# ---------- 4. Events → execution_events table ----------

@pytest.mark.asyncio
async def test_events_mirrored_into_execution_events(client, app_state, db):
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hi"},
    )

    async with db.session() as s:
        rows = (await s.execute(
            select(ExecutionEventORM)
            .where(ExecutionEventORM.session_id == sid)
            .order_by(ExecutionEventORM.created_at)
        )).scalars().all()

        types = [r.event_type for r in rows]
        # message_received + planning_started + planning_finished + workflow_created
        assert "message_received" in types
        assert "planning_started" in types
        assert "planning_finished" in types
        assert "workflow_created" in types

        # data_json must round-trip JSON-safe
        import json as _json
        for r in rows:
            payload = _json.loads(r.data_json)
            assert isinstance(payload, dict)


@pytest.mark.asyncio
async def test_pause_emits_user_paused_event_in_db(client, app_state, db):
    sid = client.post("/sessions").json()["session_id"]
    client.post(f"/sessions/{sid}/messages", json={"content": "Mở Notepad và gõ Hi"})
    client.post(f"/sessions/{sid}/pause")

    async with db.session() as s:
        row = (await s.execute(
            select(ExecutionEventORM)
            .where(
                ExecutionEventORM.session_id == sid,
                ExecutionEventORM.event_type == "user_paused",
            )
        )).scalars().first()
        assert row is not None
        import json as _json
        data = _json.loads(row.data_json)
        assert data["session_id"] == sid


# ---------- 5. Restart cycle ----------

@pytest.mark.asyncio
async def test_data_survives_app_restart(client, app_state, db):
    """Create a session + message + workflow, then re-open the same DB
    file and verify the rows are still there."""
    # Use the live fixture DB (WINDAGENT_DB_URL env var).
    sid = client.post("/sessions").json()["session_id"]
    msg = client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Restart test"},
    ).json()
    wf_id = msg["workflow_id"]
    assert wf_id

    # Close current engine (simulate shutdown).
    await db.dispose()

    # Re-open with a fresh engine against the same URL — same file on disk.
    from db.database import Database

    db2 = Database(os.environ["WINDAGENT_DB_URL"])
    try:
        async with db2.session() as s:
            sess_row = await s.get(ChatSessionORM, sid)
            assert sess_row is not None
            # Phase 5: runner auto-starts on /messages. The persisted
            # status is whatever the runner reached by the time the
            # engine was disposed.
            assert sess_row.status in {
                "planning", "pending", "running", "completed", "failed", "cancelled"
            }

            msg_row = await s.get(MessageORM, msg["message_id"])
            assert msg_row is not None
            assert msg_row.content == "Mở Notepad và gõ Restart test"

            wf_row = await s.get(WorkflowORM, wf_id)
            assert wf_row is not None
            assert wf_row.session_id == sid

            step_rows = (await s.execute(
                select(WorkflowStepORM)
                .where(WorkflowStepORM.workflow_id == wf_id)
                .order_by(WorkflowStepORM.order_index)
            )).scalars().all()
            assert len(step_rows) == 2

            events = (await s.execute(
                select(ExecutionEventORM)
                .where(ExecutionEventORM.session_id == sid)
            )).scalars().all()
            assert len(events) >= 4
    finally:
        await db2.dispose()


# ---------- 6. Tool calls table exists (Phase 3 fills it) ----------

@pytest.mark.asyncio
async def test_tool_calls_table_exists(db):
    from sqlalchemy import inspect

    async with db.engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert "tool_calls" in tables


# ---------- 7. DB created on startup ----------

@pytest.mark.asyncio
async def test_all_six_tables_created_on_startup(db):
    from sqlalchemy import inspect

    async with db.engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    expected = {
        "chat_sessions",
        "messages",
        "workflows",
        "workflow_steps",
        "tool_calls",
        "execution_events",
    }
    assert expected.issubset(set(tables))
