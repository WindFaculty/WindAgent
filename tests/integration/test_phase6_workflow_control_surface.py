"""
Phase 6 Integration Tests: Workflow Control Surface & API Parity.
Verifies GET /workflow, GET /runner, POST /pause, POST /resume, POST /stop, and POST /retry.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "apps" / "backend"))
for pkg in ["core", "storage", "orchestration", "execution", "workflows"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from db.database import Database
from db.models import AgentSessionORM, ParentTaskORM, TaskPlanORM, TaskNodeORM, ChatSessionORM
from services.event_bus import EventBus
from services.session_service import SessionService
from windagent_orchestration import OrchestrationV2Container
from windagent_execution import FakeRuntimeAdapter
from apps.backend.main import app


@pytest_asyncio.fixture
async def test_backend():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.init_models()
    app.state.db = db

    event_bus = EventBus()
    session_service = SessionService(event_bus=event_bus, db=db)
    app.state.event_bus = event_bus
    app.state.session_service = session_service

    fake_runtime = FakeRuntimeAdapter(default_mode="success")
    container = OrchestrationV2Container(uow_factory=db.session_factory)
    container.dispatcher.runtime_port = fake_runtime

    app.state.orchestration_container = container
    app.state.orchestration_dispatcher = container.dispatcher
    app.state.task_manager = container.task_manager

    session_id_str = "00000000-0000-0000-0000-000000000001"
    async with db.session() as s:
        chat_sess = ChatSessionORM(id=session_id_str, status="idle")
        sess = AgentSessionORM(
            id="agent_sess_1",
            windagent_session_id=session_id_str,
            agent_id="ag_1",
            runtime_type="hermes",
            status="idle",
        )
        pt = ParentTaskORM(id="pt_1", conversation_id=session_id_str, title="Session Plan")
        plan = TaskPlanORM(id=f"plan:{session_id_str}", parent_task_id="pt_1", status="active")
        node_1 = TaskNodeORM(id="00000000-0000-0000-0000-000000000010", plan_id=plan.id, title="Step 1", agent_type="read_file", status="completed")
        node_2 = TaskNodeORM(id="00000000-0000-0000-0000-000000000011", plan_id=plan.id, title="Step 2", agent_type="write_file", status="failed")

        s.add_all([chat_sess, sess, pt, plan, node_1, node_2])
        await s.commit()

    yield app
    await db.dispose()


@pytest.mark.asyncio
async def test_get_workflow_returns_durable_steps(test_backend):
    """The retired V1 workflow query returns the canonical tombstone."""
    sess_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/sessions/{sess_id}/workflow")
        assert resp.status_code == 410
        assert resp.json()["available_endpoints"] == "/api/v2/*"


@pytest.mark.asyncio
async def test_get_runner_state_queries_durable_facts(test_backend):
    """The retired V1 runner query returns the canonical tombstone."""
    sess_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/sessions/{sess_id}/runner")
        assert resp.status_code == 410
        assert resp.json()["status"] == 410


@pytest.mark.asyncio
async def test_pause_resume_stop_endpoints(test_backend):
    """All retired V1 mutation controls remain unavailable."""
    sess_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        r1 = await client.post(f"/api/v1/sessions/{sess_id}/pause")
        assert r1.status_code == 410

        r2 = await client.post(f"/api/v1/sessions/{sess_id}/resume")
        assert r2.status_code == 410

        r3 = await client.post(f"/api/v1/sessions/{sess_id}/stop")
        assert r3.status_code == 410
        assert {
            r1.json()["available_endpoints"],
            r2.json()["available_endpoints"],
            r3.json()["available_endpoints"],
        } == {"/api/v2/*"}


@pytest.mark.asyncio
async def test_retry_step_endpoint(test_backend):
    """The retired V1 retry endpoint returns the canonical tombstone."""
    step_id = "00000000-0000-0000-0000-000000000011"
    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        resp = await client.post(f"/api/v1/workflow/{step_id}/retry")
        assert resp.status_code == 410
        assert resp.json()["available_endpoints"] == "/api/v2/*"
