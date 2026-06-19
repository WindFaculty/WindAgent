"""WebSocket integration tests using a real uvicorn server.

The in-process httpx-ws ASGI transport deadlocks during teardown because
the WebSocket handler task is still alive when the test's event loop is
closed. Running the app on a real port (via uvicorn.Server in a
background asyncio task) and connecting with the `websockets` client
gives us a faithful round-trip without in-process weirdness.
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
    """Start the FastAPI app on a free port. Yield (http_base, ws_base)."""
    from main import app

    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start within 10s")

    http_base = f"http://127.0.0.1:{port}"
    ws_base = f"ws://127.0.0.1:{port}"
    try:
        yield http_base, ws_base
    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=5.0)


@pytest.fixture
async def running_app() -> AsyncIterator[tuple[str, str]]:
    async with _running_app() as bases:
        yield bases


async def _receive_event(ws, timeout: float = 5.0) -> dict:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if raw == "ping":
        return await _receive_event(ws, timeout)
    return json.loads(raw)


@pytest.mark.asyncio
async def test_ws_receives_full_planning_sequence(running_app):
    http_base, ws_base = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sess = (await http.post("/sessions")).json()
        sid = sess["session_id"]

        async with websockets.connect(f"{ws_base}/ws/{sid}") as ws:
            resp = await http.post(
                f"/sessions/{sid}/messages",
                json={"content": "Mở Notepad và gõ Hello"},
            )
            assert resp.status_code == 202
            body = resp.json()
            assert body["workflow_id"]

            events = []
            for _ in range(4):
                events.append(await _receive_event(ws))
            assert [e["event"] for e in events] == [
                "message_received",
                "planning_started",
                "planning_finished",
                "workflow_created",
            ]


@pytest.mark.asyncio
async def test_ws_receives_user_paused_event(running_app):
    http_base, ws_base = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sid = (await http.post("/sessions")).json()["session_id"]
        async with websockets.connect(f"{ws_base}/ws/{sid}") as ws:
            await http.post(
                f"/sessions/{sid}/messages",
                json={"content": "Mở Notepad và gõ Hi"},
            )
            for _ in range(4):
                await _receive_event(ws)
            resp = await http.post(f"/sessions/{sid}/pause")
            assert resp.status_code == 202
            evt = await _receive_event(ws)
            assert evt["event"] == "user_paused"
            assert evt["data"]["session_id"] == sid


@pytest.mark.asyncio
async def test_ws_receives_user_resumed_event(running_app):
    http_base, ws_base = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sid = (await http.post("/sessions")).json()["session_id"]
        async with websockets.connect(f"{ws_base}/ws/{sid}") as ws:
            await http.post(
                f"/sessions/{sid}/messages", json={"content": "Mở Edge"}
            )
            for _ in range(4):
                await _receive_event(ws)
            resp = await http.post(f"/sessions/{sid}/resume")
            assert resp.status_code == 202
            evt = await _receive_event(ws)
            assert evt["event"] == "user_resumed"


@pytest.mark.asyncio
async def test_ws_receives_user_stopped_event(running_app):
    http_base, ws_base = running_app
    async with httpx.AsyncClient(base_url=http_base) as http:
        sid = (await http.post("/sessions")).json()["session_id"]
        async with websockets.connect(f"{ws_base}/ws/{sid}") as ws:
            await http.post(
                f"/sessions/{sid}/messages", json={"content": "Mở Notepad"}
            )
            for _ in range(4):
                await _receive_event(ws)
            resp = await http.post(f"/sessions/{sid}/stop")
            assert resp.status_code == 202
            evt = await _receive_event(ws)
            assert evt["event"] == "user_stopped"


@pytest.mark.asyncio
async def test_ws_unknown_session_closes(running_app):
    _, ws_base = running_app
    with pytest.raises(Exception):
        async with websockets.connect(
            f"{ws_base}/ws/00000000-0000-4000-8000-000000000999"
        ) as ws:
            await ws.recv()
