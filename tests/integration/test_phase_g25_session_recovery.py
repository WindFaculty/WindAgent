"""
Phase G25 — Agent Session recovery integration tests (V3 surface).

The V2 sessions API was retired (410 Gone). The recovery primitives these
tests exercise now live on the V3 surface:

  - conversation detail carries durable events (refresh recovery analog:
    GET /api/v3/conversations/{id} returns the event history)
  - cursor-based replay + isolation: covered exhaustively by
    tests/unit/api/test_architecture_v3_phase6_realtime.py (root /ws
    subscribe/after_sequence/catchup protocol, duplicate suppression,
    per-aggregate isolation) and the phase16 WS replay tests
  - cancel semantics: POST /api/v3/tasks/{task_id}/cancel -> CANCELLED

Kept as live integration over the real uvicorn app: proves the recovery
endpoints answer over HTTP after full lifespan startup.
"""
from __future__ import annotations

import asyncio
import contextlib
import socket
from typing import AsyncIterator

import httpx
import pytest
import uvicorn


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def _running_app() -> AsyncIterator[str]:
    from windagent_api.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start within 10s")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=5.0)


@pytest.fixture
async def running_app():
    async with _running_app() as base:
        yield base


@pytest.mark.asyncio
async def test_conversation_detail_returns_durable_events(running_app):
    """Conversation detail must carry the persisted event history (recovery read model)."""
    async with httpx.AsyncClient(base_url=running_app) as http:
        cid = (await http.post("/api/v3/conversations", json={"objective": "recovery probe"})).json()["id"]
        detail = (await http.get(f"/api/v3/conversations/{cid}")).json()

    assert detail["conversation"]["id"] == cid
    assert detail["events"], "detail must carry persisted events"
    assert any(e["event_type"] == "conversation.started" for e in detail["events"])


@pytest.mark.asyncio
async def test_cursor_replay_and_isolation_contract(running_app):
    """V2 sessions cursor-replay/isolation moved to root /ws — assert the tombstone
    points there and the canonical coverage stays in phase6 realtime suite."""
    async with httpx.AsyncClient(base_url=running_app) as http:
        r = await http.post("/api/v2/sessions", json={"title": "t"})
        assert r.status_code == 410
        assert r.json()["available_endpoints"] == "/api/v3/*"


@pytest.mark.asyncio
async def test_cancel_has_distinct_terminal_semantics(running_app):
    """cancel = terminal CANCELLED state, readable afterwards."""
    async with httpx.AsyncClient(base_url=running_app) as http:
        cid = (await http.post("/api/v3/conversations", json={"objective": "cancel probe"})).json()["id"]
        tid = (await http.post("/api/v3/tasks", json={"conversation_id": cid, "objective": "work"})).json()["id"]

        r = await http.post(f"/api/v3/tasks/{tid}/cancel")
        assert r.status_code == 200
        assert r.json()["state"] == "CANCELLED"
        got = await http.get(f"/api/v3/tasks/{tid}")
        assert got.json()["state"] == "CANCELLED"
