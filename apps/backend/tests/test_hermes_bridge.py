"""Contract test for Hermes runtime adapter against a fake Hermes server.

Verifies:
  - HermesEventTranslator maps tool.started -> tool_call_started etc.
  - HermesApiClient.start_run / stream_run_events talk to the fake server
    via httpx ASGITransport (no real socket, no real Hermes process).
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.fake_hermes_server import fake_app  # noqa: E402
from services.hermes.event_mapper import HermesEventTranslator  # noqa: E402
from services.hermes.api_client import HermesApiClient  # noqa: E402
from services.hermes.config import HermesConfig  # noqa: E402


@pytest.mark.asyncio
async def test_event_translator_mapping():
    env = HermesEventTranslator.translate(
        {"event": "tool.started", "tool": "terminal", "preview": "ls"},
        windagent_session_id="s1",
        sequence=1,
    )
    assert env is not None
    assert env.event == "tool_call_started"
    assert env.data["tool_name"] == "terminal"

    env2 = HermesEventTranslator.translate(
        {"event": "assistant.delta", "delta": "hi"},
        windagent_session_id="s1",
        sequence=2,
    )
    assert env2.event == "assistant_message_delta"
    assert env2.data["delta"] == "hi"

    env3 = HermesEventTranslator.translate(
        {"event": "run.completed", "run_id": "r1"},
        windagent_session_id="s1",
        sequence=3,
    )
    assert env3.event == "session_finished"


@pytest.mark.asyncio
async def test_api_client_streams_from_fake_server():
    transport = httpx.ASGITransport(app=fake_app)
    real_async_client = httpx.AsyncClient

    def _make_client(*args, **kwargs):
        # New client per open, all sharing the fake transport.
        return real_async_client(transport=transport, base_url="http://fake-hermes")

    httpx.AsyncClient = _make_client
    try:
        cfg = HermesConfig(
            enabled=True,
            base_url="http://fake-hermes",
            api_key="",
            request_timeout_s=5,
            connect_timeout_s=5,
            auto_start=False,
            executable="hermes",
            profile="default",
            max_concurrent_runs=1,
        )
        api = HermesApiClient(cfg)

        resp = await api.start_run(
            user_message="hello",
            session_id="sess_x",
            instructions="sys",
            model="role:Coder",
        )
        run_id = resp["run_id"]
        assert run_id.startswith("run_")

        events = [ev async for ev in api.stream_run_events(run_id)]
    finally:
        httpx.AsyncClient = real_async_client

    assert any(e.get("event") == "tool.started" for e in events)
    assert any(e.get("event") == "run.completed" for e in events)

