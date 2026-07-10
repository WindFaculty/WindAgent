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

    env4 = HermesEventTranslator.translate(
        {"event": "tool.progress", "tool": "terminal", "progress": "scanning"},
        windagent_session_id="s1",
        sequence=4,
    )
    assert env4.event == "tool_call_progress"
    assert env4.data["progress"] == "scanning"

    env5 = HermesEventTranslator.translate(
        {"event": "run.failed", "run_id": "r1", "error": "Something crashed"},
        windagent_session_id="s1",
        sequence=5,
    )
    assert env5.event == "session_finished"
    assert env5.data["final_status"] == "failed"
    assert env5.data["error"]["message"] == "Something crashed"


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


@pytest.mark.asyncio
async def test_api_client_new_endpoints():
    transport = httpx.ASGITransport(app=fake_app)
    real_async_client = httpx.AsyncClient

    def _make_client(*args, **kwargs):
        return real_async_client(transport=transport, base_url="http://fake-hermes")

    httpx.AsyncClient = _make_client
    try:
        cfg = HermesConfig(
            enabled=True,
            base_url="http://fake-hermes",
            api_key="super_secret_key_123",
            request_timeout_s=5,
            connect_timeout_s=5,
            auto_start=False,
        )
        api = HermesApiClient(cfg)

        # Test health
        health = await api.get_health()
        assert health["status"] == "healthy"

        # Test detailed health
        detailed = await api.get_detailed_health()
        assert detailed["status"] == "healthy"
        assert detailed["database"] == "connected"

        # Test capabilities
        caps = await api.get_capabilities()
        assert caps["version"] == "0.18.2"

        # Test models
        models = await api.get_models()
        assert len(models["models"]) == 2

        # Test toolsets
        tools = await api.get_toolsets()
        assert "terminal" in tools["toolsets"]

        # Test skills
        skills = await api.get_skills()
        assert "python_coding" in skills["skills"]

    finally:
        httpx.AsyncClient = real_async_client


def test_hermes_config_secret_scrubbing():
    cfg = HermesConfig(
        enabled=True,
        api_key="secret-api-key-xyz",
        base_url="http://localhost:8642"
    )
    # Check repr scrubs key
    r = repr(cfg)
    assert "secret-api-key-xyz" not in r
    assert "[REDACTED]" in r

    # Check scrubbed dict
    d = cfg.get_scrubbed_dict()
    assert d["api_key"] == "[REDACTED]"


def test_hermes_router_endpoints(monkeypatch):
    from main import app
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock
    from services.hermes.runtime_manager import HermesRuntimeManager

    # Prevent real process manager start/probe delays during app lifespan
    monkeypatch.setattr(HermesRuntimeManager, "start", AsyncMock())
    monkeypatch.setattr(HermesRuntimeManager, "probe_health", AsyncMock(return_value=True))

    # Create mock manager and client
    mock_mgr = MagicMock()
    mock_mgr.status = "healthy"
    mock_mgr.config.enabled = True
    mock_mgr.config.auto_start = True
    mock_mgr.config.executable = "hermes"
    mock_mgr.config.base_url = "http://fake-hermes"
    mock_mgr.config.api_key = "secret_key"
    mock_mgr.config.profile = "windagent"
    
    async def mock_probe_health():
        return True
    
    async def mock_get_capabilities():
        return {"version": "0.18.2", "api_server": True}

    mock_mgr.probe_health = mock_probe_health
    mock_mgr.get_capabilities = mock_get_capabilities

    mock_api = MagicMock()
    
    async def mock_api_get_capabilities():
        return {"version": "0.18.2", "api_server": True}
        
    async def mock_api_get_detailed_health():
        return {"status": "healthy", "uptime_s": 5000}
        
    async def mock_api_get_toolsets():
        return {"toolsets": ["terminal"]}
        
    async def mock_api_get_skills():
        return {"skills": ["coding"]}

    mock_api.get_capabilities = mock_api_get_capabilities
    mock_api.get_detailed_health = mock_api_get_detailed_health
    mock_api.get_toolsets = mock_api_get_toolsets
    mock_api.get_skills = mock_api_get_skills

    try:
        with TestClient(app) as client:
            # Overwrite after lifespan has initialized state
            client.app.state.hermes_runtime_manager = mock_mgr
            client.app.state.hermes_api_client = mock_api

            # 1. status
            resp = client.get("/api/v1/runtimes/hermes/status")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

            # 2. health
            resp = client.get("/api/v1/runtimes/hermes/health")
            assert resp.status_code == 200
            assert resp.json()["reachable"] is True
            assert resp.json()["api_key_scrubbed"] is True

            # 3. health/detailed
            resp = client.get("/api/v1/runtimes/hermes/health/detailed")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

            # 4. capabilities
            resp = client.get("/api/v1/runtimes/hermes/capabilities")
            assert resp.status_code == 200
            assert resp.json()["version"] == "0.18.2"

            # 5. tools
            resp = client.get("/api/v1/runtimes/hermes/tools")
            assert resp.status_code == 200
            assert "terminal" in resp.json()["toolsets"]["toolsets"]
            assert "coding" in resp.json()["skills"]["skills"]
    finally:
        pass


@pytest.mark.asyncio
async def test_hermes_session_mapping_and_sync(client, db):
    from db.models import AgentORM, AgentSessionORM
    from sqlalchemy import select
    # 1. Register a hermes agent
    async with db.session() as s:
        agent = AgentORM(
            id="hermes_test_agent",
            name="Hermes Test Agent",
            runtime_type="hermes",
            router_role="Coder",
            system_prompt="You are a coder.",
            workspace_root=".",
        )
        s.add(agent)
        await s.commit()

    # Intercept httpx calls to point to fake_app
    transport = httpx.ASGITransport(app=fake_app)
    real_async_client = httpx.AsyncClient

    def _make_client(*args, **kwargs):
        return real_async_client(transport=transport, base_url="http://fake-hermes")

    httpx.AsyncClient = _make_client
    try:
        # 2. Create session with this agent
        resp = client.post("/api/v1/sessions", json={"agent_id": "hermes_test_agent"})
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        assert sid

        # Check session mapping in DB
        async with db.session() as s:
            stmt = select(AgentSessionORM).where(AgentSessionORM.windagent_session_id == sid)
            res = await s.execute(stmt)
            agent_sess = res.scalar_one_or_none()
            assert agent_sess is not None
            assert agent_sess.hermes_session_id is not None

        # 3. Call GET /messages which should trigger sync
        msg_resp = client.get(f"/api/v1/sessions/{sid}/messages")
        assert msg_resp.status_code == 200
        msgs = msg_resp.json()
        
        # Verify both messages from fake_hermes_server were synced
        assert len(msgs) == 2
        assert msgs[0]["sender"] == "user"
        assert msgs[0]["content"] == "Hello Hermes"
        assert msgs[1]["sender"] == "assistant"
        assert msgs[1]["content"] == "Hello! How can I help you today?"

    finally:
        httpx.AsyncClient = real_async_client


@pytest.mark.asyncio
async def test_hermes_interactive_approval(client, db):
    import asyncio
    from db.models import AgentORM, PermissionRequestORM
    from sqlalchemy import select
    # 1. Register hermes agent
    async with db.session() as s:
        agent = AgentORM(
            id="hermes_approval_agent",
            name="Hermes Approval Agent",
            runtime_type="hermes",
            router_role="Coder",
            system_prompt="sys",
            workspace_root=".",
        )
        s.add(agent)
        await s.commit()

    transport = httpx.ASGITransport(app=fake_app)
    real_async_client = httpx.AsyncClient

    def _make_client(*args, **kwargs):
        return real_async_client(transport=transport, base_url="http://fake-hermes")

    httpx.AsyncClient = _make_client
    try:
        # Create session
        sess_resp = client.post("/api/v1/sessions", json={"agent_id": "hermes_approval_agent"})
        assert sess_resp.status_code == 201
        sid = sess_resp.json()["session_id"]

        # Connect WebSocket
        with client.websocket_connect(f"/ws/{sid}") as ws:
            # Send message that triggers approval.request
            msg_resp = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": "delete database"})
            assert msg_resp.status_code == 202
            
            # Read WebSocket events to find the permission request
            permission_req = None
            for i in range(10):
                try:
                    # Use a short timeout to prevent hanging
                    data = ws.receive_json()
                    print(f"WS received event {i}:", data)
                    if data.get("event") == "permission_request":
                        permission_req = data
                        break
                except Exception as ex:
                    print(f"WS error {i}:", ex)
            
            assert permission_req is not None
            req_id = permission_req["data"]["request_id"]
            assert req_id

            # Verify status is pending in DB
            async with db.session() as s:
                stmt = select(PermissionRequestORM).where(PermissionRequestORM.windagent_request_id == req_id)
                res = await s.execute(stmt)
                row = res.scalar_one_or_none()
                assert row is not None
                assert row.status == "pending"
                run_id = row.run_id

            # Send permission choice over websocket control message
            ws.send_json({
                "action": "permission_granted",
                "request_id": req_id
            })

            # Wait a brief moment for database update
            await asyncio.sleep(0.05)

            # Verify status is granted in DB
            async with db.session() as s:
                stmt = select(PermissionRequestORM).where(PermissionRequestORM.windagent_request_id == req_id)
                res = await s.execute(stmt)
                row = res.scalar_one_or_none()
                assert row.status == "granted"

            # Check that fake server recorded choice 'once'
            from tests.fake_hermes_server import _RUNS
            assert _RUNS[run_id]["approved"] == "once"

    finally:
        httpx.AsyncClient = real_async_client


