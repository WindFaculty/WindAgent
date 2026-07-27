"""Phase G25 — Agent Session recovery integration tests.

These exercise the REAL backend (uvicorn server + websockets + SQLite) to
verify the recovery primitives the frontend is supposed to rely on:

  - snapshot API returns messages + last_event_sequence
  - cursor-based event replay (reconnect after disconnect)
  - multi-session isolation (events never cross sessions)
  - cancel / archive / delete have DISTINCT backend semantics

Run with: pytest tests/integration/test_phase_g25_session_recovery.py -q
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from typing import AsyncIterator

import httpx
import pytest
import uvicorn
import websockets


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def _running_app() -> AsyncIterator[tuple[str, str]]:
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
        yield f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=5.0)


@pytest.fixture
async def running_app():
    async with _running_app() as bases:
        yield bases


async def _recv(ws, timeout: float = 5.0) -> dict:
    """Receive a non-ping message from websocket, skipping heartbeats."""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    try:
        data = json.loads(raw)
        if data.get("type") == "ping":
            # One level of ping skipping - if next is also ping, return it
            return await _recv_once(ws, timeout)
        return data
    except json.JSONDecodeError:
        if raw == "ping":
            return await _recv_once(ws, timeout)
        raise


async def _recv_once(ws, timeout: float = 5.0) -> dict:
    """Receive a single message without ping skipping."""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


@pytest.mark.asyncio
async def test_snapshot_returns_messages_and_sequence(running_app):
    """Backend snapshot must carry history + last_event_sequence for refresh recovery."""
    http_base, _ = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        # Use V2 sessions endpoint
        sid = (await http.post("/api/v2/sessions", json={"title": "test"})).json()["session_id"]
        await http.post(f"/api/v2/sessions/{sid}/messages", json={"content": "hello"})
        await asyncio.sleep(0.3)

        snap = (await http.get(f"/api/v2/sessions/{sid}/snapshot")).json()

    assert snap["session"]["id"] == sid
    assert snap["last_event_sequence"] >= 1, "snapshot must report persisted seq"
    assert any(m["sender"] == "user" for m in snap["messages"]), "snapshot must carry messages"
    # NOTE (finding): snapshot omits agent_id even though DB stores it.
    assert "agent_id" not in snap["session"], "snapshot does not expose agent_id (gap)"


@pytest.mark.asyncio
async def test_reconnect_replays_missed_events_by_cursor(running_app):
    """Cursor-based replay: posting messages then asking for events after_seq
    must return ONLY the events with seq > after_seq (the reconnect contract)."""
    http_base, _ = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sid = (await http.post("/api/v2/sessions", json={"title": "test"})).json()["session_id"]

        # First message batch
        await http.post(f"/api/v2/sessions/{sid}/messages", json={"content": "first"})
        await asyncio.sleep(0.3)
        first = (await http.get(f"/api/v2/sessions/{sid}/events?after_seq=0")).json()
        seqs = [e.get("seq") for e in first["events"] if e.get("seq")]
        assert seqs, "events must carry seq"
        after = max(seqs)

        # Second message batch generates NEW events (seq > after)
        await http.post(f"/api/v2/sessions/{sid}/messages", json={"content": "second"})
        await asyncio.sleep(0.3)
        second = (await http.get(f"/api/v2/sessions/{sid}/events?after_seq={after}")).json()

        replay_seqs = [e.get("seq") for e in second["events"] if e.get("seq")]
        assert replay_seqs, f"expected new events after reconnect, got {second['events']}"
        assert all(s > after for s in replay_seqs), f"replay must skip <= {after}, got {replay_seqs}"
        # The newly sent message must be present in the replayed events.
        assert any(
            e.get("event_type") == "message_received" and e["data"].get("content") == "second"
            for e in second["events"]
        )


@pytest.mark.asyncio
async def test_multi_session_isolation(running_app):
    """Events for session A must never reach session B's socket.

    Session B will receive heartbeat pings (every 0.05s) but should NOT receive
    the message_received event from session A.
    """
    http_base, ws_base = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        a = (await http.post("/api/v2/sessions", json={"title": "A"})).json()["session_id"]
        b = (await http.post("/api/v2/sessions", json={"title": "B"})).json()["session_id"]

        # Connect to V2 events websocket with session-specific aggregate_id filtering
        async with websockets.connect(f"{ws_base}/api/v2/events/ws?aggregate_id={a}") as wsa, \
                   websockets.connect(f"{ws_base}/api/v2/events/ws?aggregate_id={b}") as wsb:
            await http.post(f"/api/v2/sessions/{a}/messages", json={"content": "for A"})
            evt_a = await _recv(wsa)
            assert evt_a["event_type"] == "message_received"

            # Session B receives pings, not message events - verify it never gets message_received
            messages_b = []
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < 1.0:
                try:
                    msg = await asyncio.wait_for(wsb.recv(), timeout=0.2)
                    messages_b.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify no message_received event reached session B
            event_types = [m.get("event_type") for m in messages_b if "event_type" in m]
            assert "message_received" not in event_types, f"Session B received cross-session event: {messages_b}"


@pytest.mark.asyncio
async def test_cancel_archive_delete_have_distinct_semantics(running_app):
    """cancel = stop but keep; archive = hide but keep; delete = gone."""
    http_base, _ = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sid = (await http.post("/api/v2/sessions", json={"title": "test"})).json()["session_id"]

        r = await http.post(f"/api/v2/sessions/{sid}/cancel")
        assert r.status_code == 204
        got = (await http.get(f"/api/v2/sessions/{sid}")).json()
        assert got["status"].lower() == "cancelled"

        r = await http.post(f"/api/v2/sessions/{sid}/archive")
        assert r.status_code == 204
        assert (await http.get(f"/api/v2/sessions/{sid}")).status_code == 200
        listed = (await http.get("/api/v2/sessions")).json()
        assert all(s["session_id"] != sid for s in listed), "archived session must leave default list"
        listed_all = (await http.get("/api/v2/sessions?exclude_archived=false")).json()
        assert any(s["session_id"] == sid for s in listed_all)

        r = await http.delete(f"/api/v2/sessions/{sid}")
        assert r.status_code == 204
        assert (await http.get(f"/api/v2/sessions/{sid}")).status_code == 404