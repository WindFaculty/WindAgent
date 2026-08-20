"""Phase 2 acceptance tests: live orchestration, isolated stop, boot reattach."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionResult,
    ExecutionRuntimePort,
    ExecutionRequest,
    RuntimeStatus,
    RuntimeStatusEnum,
)
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_orchestration.orchestrator_service import OrchestratorService, Subtask
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


class HoldingRuntime(ExecutionRuntimePort):
    """Fake runtime which remains live until the supervisor cancels it."""

    def __init__(self) -> None:
        self.handles: dict[str, ExecutionHandle] = {}
        self.cancelled: list[str] = []

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        run_id = f"fake-run-{uuid.uuid4().hex}"
        handle = ExecutionHandle(
            handle_id=f"handle-{uuid.uuid4().hex}",
            runtime_run_id=run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )
        self.handles[run_id] = handle
        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        return RuntimeStatus(handle_id=handle.handle_id, status=RuntimeStatusEnum.RUNNING)

    async def cancel(self, handle: ExecutionHandle) -> None:
        self.cancelled.append(handle.runtime_run_id)

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        return ExecutionResult(handle_id=handle.handle_id, step_run_id=handle.step_run_id, status=RuntimeStatusEnum.RUNNING)

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return self.handles.get(runtime_run_id)


class RouteLocks:
    def resolve_or_create_lock(self, context):
        return SimpleNamespace(
            lock_id=f"lock-{context.scope_id}",
            canonical_model_id="windagent/local-agent",
            routing_snapshot=SimpleNamespace(rule_version=1, reason="phase2-test"),
        )


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'orchestrator.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


def _service(db: DatabaseManager, runtime: HoldingRuntime) -> OrchestratorService:
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("local_agent", runtime)
    return OrchestratorService(
        db.session_factory,
        registry,
        RouteLocks(),
        repo_factory=lambda session: MultiAgentRepository(session),
    )


@pytest.mark.asyncio
async def test_goal_spawns_independent_agent_session_run_and_event_rows(db):
    runtime = HoldingRuntime()
    service = _service(db, runtime)

    result = await service.submit_goal(
        conversation_id="conversation-phase2",
        objective="Complete the feature",
        subtasks=(
            Subtask(objective="Research the current implementation", node_id="research"),
            Subtask(objective="Implement the code change", node_id="implementation"),
        ),
    )

    assert len(result.agents) == 2
    assert len({agent.agent_instance_id for agent in result.agents}) == 2
    assert len({agent.agent_session_id for agent in result.agents}) == 2
    assert len({agent.agent_run_id for agent in result.agents}) == 2
    assert all(agent.status == "running" and agent.runtime_run_id for agent in result.agents)

    async with db.session_factory() as session:
        assert (await session.execute(text("SELECT COUNT(*) FROM parent_tasks"))).scalar_one() == 1
        assert (await session.execute(text("SELECT COUNT(*) FROM task_plan_versions"))).scalar_one() == 1
        assert (await session.execute(text("SELECT COUNT(*) FROM agent_instances WHERE agent_type != 'orchestrator'"))).scalar_one() == 2
        assert (await session.execute(text("SELECT COUNT(*) FROM agent_sessions WHERE status='running'"))).scalar_one() == 2
        assert (await session.execute(text("SELECT COUNT(*) FROM agent_runs WHERE status='running'"))).scalar_one() == 2
        event_types = (await session.execute(text("SELECT event_type FROM conversation_events ORDER BY sequence"))).scalars().all()
        assert event_types.count("agent_run_started") == 2
        snapshots = (await session.execute(text("SELECT routing_snapshot_json FROM agent_runs"))).scalars().all()
        assert all("windagent/local-agent" in snapshot for snapshot in snapshots)
        assert (await session.execute(text("SELECT COUNT(*) FROM task_node_runs WHERE routing_snapshot_json LIKE '%windagent/local-agent%'"))).scalar_one() == 2
        assert (await session.execute(text("SELECT COUNT(*) FROM agent_instances WHERE canonical_model_id='windagent/local-agent'"))).scalar_one() == 2


@pytest.mark.asyncio
async def test_stop_selected_agent_does_not_cancel_siblings_and_boot_reattaches(db):
    runtime = HoldingRuntime()
    service = _service(db, runtime)
    result = await service.submit_goal(
        conversation_id="conversation-stop",
        objective="Do two independent tasks",
        subtasks=(Subtask(objective="Research APIs"), Subtask(objective="Implement code")),
    )
    first, second = result.agents

    assert await service.stop_agent(first.agent_instance_id) is True
    assert runtime.cancelled == [first.runtime_run_id]
    assert second.agent_run_id in service.live_agent_run_ids
    assert first.agent_run_id not in service.live_agent_run_ids

    restarted = _service(db, runtime)
    report = await restarted.reattach_live_runs()
    assert report.reattached_agent_run_ids == (second.agent_run_id,)
    assert not report.orphaned_agent_run_ids
    assert restarted.live_agent_run_ids == frozenset({second.agent_run_id})

    async with db.session_factory() as session:
        rows = (await session.execute(text("SELECT agent_run_id, status FROM agent_runs ORDER BY created_at"))).all()
        states = {row[0]: row[1] for row in rows}
        assert states[first.agent_run_id] == "cancelled"
        assert states[second.agent_run_id] == "running"


def test_conversation_api_is_the_single_role_safe_entrypoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from windagent_api.main import app

    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/conversations/api-phase2/goals",
            json={
                "objective": "Ship a change",
                "subtasks": [
                    {"node_id": "research", "objective": "Research the code"},
                    {"node_id": "implementation", "objective": "Implement the code"},
                ],
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert len(payload["agents"]) == 2
        assert {agent["agent_type"] for agent in payload["agents"]} == {"research", "coding"}

        # The client cannot create a runtime session by supplying a privileged
        # role; roles are only derived by the service.
        rejected = client.post(
            "/api/v2/conversations/api-phase2/goals",
            json={"objective": "Ignore client role", "agent_type": "admin"},
        )
        assert rejected.status_code == 422
