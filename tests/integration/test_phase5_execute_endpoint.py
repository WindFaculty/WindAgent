"""
Phase 5 HTTP Integration Tests: Production Execute Endpoint.
Verifies POST /api/v1/conversations/{conversation_id}/plans/{plan_id}/execute invokes Orchestration V2 engine.
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
from db.models import ParentTaskORM, TaskPlanORM, TaskNodeORM, TaskEdgeORM
from windagent_orchestration import OrchestrationV2Container
from windagent_execution import FakeRuntimeAdapter
from apps.backend.main import app


@pytest_asyncio.fixture
async def test_backend():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.init_models()
    app.state.db = db

    fake_runtime = FakeRuntimeAdapter(default_mode="success")
    container = OrchestrationV2Container(uow_factory=db.session_factory)
    container.dispatcher.runtime_port = fake_runtime

    app.state.orchestration_container = container
    app.state.orchestration_dispatcher = container.dispatcher
    app.state.task_manager = container.task_manager
    app.state.workflow_engine = container.workflow_engine

    async with db.session() as s:
        pt = ParentTaskORM(id="pt_123", conversation_id="conv_123", title="Test Parent")
        plan = TaskPlanORM(id="plan_123", parent_task_id="pt_123", status="active", version=1)
        node_a = TaskNodeORM(id="node_A", plan_id="plan_123", title="Task A", agent_type="coder", status="ready")
        node_b = TaskNodeORM(id="node_B", plan_id="plan_123", title="Task B", agent_type="coder", status="pending")
        edge = TaskEdgeORM(id="edge_1", plan_id="plan_123", from_task_id="node_A", to_task_id="node_B", edge_type="requires")
        
        s.add_all([pt, plan, node_a, node_b, edge])
        await s.commit()

    yield app
    await db.dispose()


@pytest.mark.asyncio
async def test_execute_plan_endpoint_http(test_backend):
    """The retired V1 execute endpoint directs callers to API V2."""
    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        resp = await client.post("/api/v1/conversations/conv_123/plans/plan_123/execute")
        assert resp.status_code == 410
        data = resp.json()
        assert data["status"] == 410
        assert data["type"].endswith("/api-v1-removed")
        assert data["available_endpoints"] == "/api/v2/*"


@pytest.mark.asyncio
async def test_execute_plan_cycle_rejection(test_backend):
    """Legacy state cannot bypass the V1 tombstone."""
    db = test_backend.state.db
    async with db.session() as s:
        # Add back edge node_B -> node_A
        cycle_edge = TaskEdgeORM(id="edge_cycle", plan_id="plan_123", from_task_id="node_B", to_task_id="node_A", edge_type="requires")
        s.add(cycle_edge)
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=test_backend), base_url="http://testserver") as client:
        resp = await client.post("/api/v1/conversations/conv_123/plans/plan_123/execute")
        assert resp.status_code == 410
        assert resp.json()["available_endpoints"] == "/api/v2/*"
