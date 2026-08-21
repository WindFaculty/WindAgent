"""
Phase 5 HTTP Integration Tests: Production Execute Endpoint.
Verifies POST /api/v1/conversations/{conversation_id}/plans/{plan_id}/execute invokes Orchestration V2 engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_orchestration import OrchestrationV2Container
from windagent_execution import FakeRuntimeAdapter
from windagent_api.main import app


@pytest_asyncio.fixture
async def test_backend():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    app.state.db = db

    fake_runtime = FakeRuntimeAdapter(default_mode="success")
    container = OrchestrationV2Container(uow_factory=db.session_factory)
    container.dispatcher.runtime_port = fake_runtime

    app.state.orchestration_container = container
    app.state.orchestration_dispatcher = container.dispatcher
    app.state.task_manager = container.task_manager
    app.state.workflow_engine = container.workflow_engine

    yield app
    await db.close()


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