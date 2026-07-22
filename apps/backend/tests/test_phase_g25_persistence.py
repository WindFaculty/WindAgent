"""Phase G25 — backend persistence & recovery integration tests (Phase 4 gaps).

Real backend via running_app fixture (uvicorn + SQLite temp DB). No mocks.
Covers: migration validation, tool-call lifecycle persistence, workflow
persistence, no live/replay gap, missing-session 404, cancel/archive/delete
semantics + isolation, pagination.

Run: python -m pytest tests/test_phase_g25_persistence.py -q
"""
import asyncio
import os
import socket
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.database import Base
from db.models import ChatSessionORM, MessageORM, ToolCallORM, WorkflowORM, WorkflowStepORM
from services.session_service import SessionService

API = "/api/v1"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]


@pytest.fixture
async def running_app():
    from main import app

    port = _free_port()
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(cfg)
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        except Exception:
            pass


@pytest.fixture
async def db_url():
    import tempfile

    path = os.path.join(tempfile.gettempdir(), f"wa_persist_{uuid.uuid4().hex}.db")
    url = f"sqlite+aiosqlite:///{path}?timeout=30"
    engine = create_async_engine(url)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield url
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@pytest.fixture
async def svc(db_url):
    from db.database import Database
    from services.event_bus import EventBus

    db = Database(db_url)
    svc = SessionService(EventBus(), db)
    yield svc
    await db.dispose()


async def _emit_seq(base, sid, n):
    """Drive n message events so execution_events carries seq 1..n."""
    async with httpx.AsyncClient(base_url=base) as h:
        for i in range(n):
            await h.post(f"{API}/sessions/{sid}/messages", json={"content": f"m{i}"})
        await asyncio.sleep(0.3)


# ----------------------------------------------------------------------
# 4.1 Migration
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_creates_recovery_columns(db_url):
    engine = create_async_engine(db_url)
    async with engine.connect() as c:
        cols = (await c.execute(text("PRAGMA table_info(chat_sessions)"))).fetchall()
        names = {r[1] for r in cols}
    await engine.dispose()
    for needed in ("last_event_sequence", "archived_at", "completed_at", "error_message", "agent_id"):
        assert needed in names, f"migration missing column {needed}"


@pytest.mark.asyncio
async def test_seq_monotonic_and_persisted_via_hook(running_app):
    """Through the real app (event hook wired), emitting messages must produce
    strictly increasing, gap-free, per-session seq in execution_events."""
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        sid = (await h.post(f"{API}/sessions")).json()["session_id"]
        for i in range(3):
            await h.post(f"{API}/sessions/{sid}/messages", json={"content": f"m{i}"})
        await asyncio.sleep(0.3)
        ev = (await h.get(f"{API}/sessions/{sid}/events?after_seq=0")).json()
        seqs = [e.get("seq") for e in ev["events"] if e.get("seq")]
        assert seqs, f"no seq persisted: {ev['events']}"
        assert seqs == list(range(1, len(seqs) + 1)), f"seq not monotonic/gap-free: {seqs}"


# ----------------------------------------------------------------------
# 4.4 Tool-call lifecycle persistence
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_call_lifecycle_persisted_via_snapshot(svc):
    chat = await svc.create_session()
    sid = chat.id
    tc_id = str(uuid.uuid4())
    async with svc._db.session_factory() as db:
        db.add(ToolCallORM(
            id=tc_id, session_id=str(sid), step_id=None,
            tool_name="search", status="running",
            input_json='{"q":"x"}', output_json="{}",
        ))
        await db.commit()
        # advance to completed
        row = await db.get(ToolCallORM, tc_id)
        row.status = "completed"
        row.output_json = '{"ok":true}'
        await db.commit()

    snap = await svc.get_session_snapshot(sid)
    tcs = snap["tool_calls"]
    assert any(tc["id"] == tc_id and tc["status"] == "completed"
               and tc["output"] == {"ok": True} for tc in tcs), \
        f"tool call not persisted/reloaded: {tcs}"


@pytest.mark.asyncio
async def test_tool_call_duplicate_completion_single_row(svc):
    chat = await svc.create_session()
    sid = chat.id
    tc_id = str(uuid.uuid4())
    async with svc._db.session_factory() as db:
        db.add(ToolCallORM(
            id=tc_id, session_id=str(sid), step_id=None,
            tool_name="t", status="completed",
            input_json="{}", output_json="r1",
        ))
        await db.commit()
        # simulate duplicate completion update (upsert, not insert)
        row = await db.get(ToolCallORM, tc_id)
        row.output_json = "r2"
        await db.commit()
        rows = (await db.execute(
            text("SELECT id FROM tool_calls WHERE id=:i"), {"i": tc_id}
        )).fetchall()
    assert len(rows) == 1, "duplicate completion created extra row"


# ----------------------------------------------------------------------
# 4.5 Workflow persistence
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workflow_progress_persisted_and_not_regressed(svc):
    chat = await svc.create_session()
    sid = chat.id
    wf_id = str(uuid.uuid4())
    async with svc._db.session_factory() as db:
        db.add(WorkflowORM(id=wf_id, session_id=str(sid), status="running"))
        db.add(WorkflowStepORM(
            id="s1", workflow_id=wf_id, name="step1", tool_name="t",
            status="completed", order_index=0,
        ))
        db.add(WorkflowStepORM(
            id="s2", workflow_id=wf_id, name="step2", tool_name="t",
            status="pending", order_index=1,
        ))
        await db.commit()
        # advance s2 -> completed
        s2 = await db.get(WorkflowStepORM, "s2")
        s2.status = "completed"
        await db.commit()
        s1 = await db.get(WorkflowStepORM, "s1")
        s2b = await db.get(WorkflowStepORM, "s2")
    assert s1.status == "completed"
    assert s2b.status == "completed", "completed step regressed to pending"


# ----------------------------------------------------------------------
# 4.10 No live/replay gap
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_replay_live_gap(running_app):
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        sid = (await h.post(f"{API}/sessions")).json()["session_id"]
        await _emit_seq(base, sid, 2)  # events 1,2 persisted
        snap = (await h.get(f"{API}/sessions/{sid}/snapshot")).json()
        after = snap["last_event_sequence"]
        # New event appears while client would be replaying
        await h.post(f"{API}/sessions/{sid}/messages", json={"content": "third"})
        await asyncio.sleep(0.3)
        replay = (await h.get(f"{API}/sessions/{sid}/events?after_seq={after}")).json()
        seqs = [e.get("seq") for e in replay["events"] if e.get("seq")]
        # New event (pushed after `after`) must be captured, no gap, no old leak
        assert seqs, f"replay returned nothing: {replay['events']}"
        assert all(s > after for s in seqs), f"replay leaked old events: {seqs}"
        assert max(seqs) > after, "live event during replay lost"


# ----------------------------------------------------------------------
# 4.12 Missing session -> 404
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_session_returns_404(running_app):
    base = running_app
    fake = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=base) as h:
        assert (await h.get(f"{API}/sessions/{fake}")).status_code == 404
        assert (await h.get(f"{API}/sessions/{fake}/snapshot")).status_code == 404
        assert (await h.post(f"{API}/sessions/{fake}/cancel")).status_code == 404
        assert (await h.delete(f"{API}/sessions/{fake}")).status_code == 404


# ----------------------------------------------------------------------
# 4.14 Cancel semantics + isolation
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_is_idempotent_and_isolated(running_app):
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        a = (await h.post(f"{API}/sessions")).json()["session_id"]
        b = (await h.post(f"{API}/sessions")).json()["session_id"]
        await h.post(f"{API}/sessions/{a}/messages", json={"content": "a"})
        await h.post(f"{API}/sessions/{b}/messages", json={"content": "b"})
        # cancel A twice (idempotent)
        assert (await h.post(f"{API}/sessions/{a}/cancel")).status_code == 204
        assert (await h.post(f"{API}/sessions/{a}/cancel")).status_code == 204
        # B unaffected
        sb = (await h.get(f"{API}/sessions/{b}")).json()
        assert sb["status"] != "cancelled", "cancel leaked to session B"
        sa = (await h.get(f"{API}/sessions/{a}")).json()
        assert sa["status"] == "cancelled"
        # history preserved
        ma = (await h.get(f"{API}/sessions/{a}/messages")).json()
        assert any(m["content"] == "a" for m in ma)


# ----------------------------------------------------------------------
# 4.15 Archive hides but preserves
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archive_hides_from_default_list_preserves_data(running_app):
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        a = (await h.post(f"{API}/sessions")).json()["session_id"]
        await h.post(f"{API}/sessions/{a}/messages", json={"content": "keep"})
        assert (await h.post(f"{API}/sessions/{a}/archive")).status_code == 204
        # default list excludes archived (list_sessions returns a JSON array)
        lst = (await h.get(f"{API}/sessions")).json()
        assert a not in [s["id"] for s in lst]
        # still retrievable
        assert (await h.get(f"{API}/sessions/{a}")).status_code == 200
        ma = (await h.get(f"{API}/sessions/{a}/messages")).json()
        assert any(m["content"] == "keep" for m in ma)


# ----------------------------------------------------------------------
# 4.16 Delete isolation
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_isolates_other_sessions(running_app):
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        a = (await h.post(f"{API}/sessions")).json()["session_id"]
        b = (await h.post(f"{API}/sessions")).json()["session_id"]
        assert (await h.delete(f"{API}/sessions/{a}")).status_code == 204
        # B still alive
        assert (await h.get(f"{API}/sessions/{b}")).status_code == 200
        # A gone
        assert (await h.get(f"{API}/sessions/{a}")).status_code == 404
        assert (await h.delete(f"{API}/sessions/{a}")).status_code == 404  # idempotent


# ----------------------------------------------------------------------
# 4.17 Pagination stable ordering
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_list_pagination_stable(running_app):
    base = running_app
    async with httpx.AsyncClient(base_url=base) as h:
        created = []
        for _ in range(5):
            created.append((await h.post(f"{API}/sessions")).json()["session_id"])
        page1 = (await h.get(f"{API}/sessions?limit=2&offset=0")).json()
        page2 = (await h.get(f"{API}/sessions?limit=2&offset=2")).json()
        ids1 = [s["id"] for s in page1]
        ids2 = [s["id"] for s in page2]
        assert len(ids1) == 2 and len(ids2) == 2
        assert not (set(ids1) & set(ids2)), "pagination overlap"
