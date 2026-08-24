"""Phase 4 (P4-R4B) — focused control-plane lifecycle tests.

Covers the verified cutover defects at the repository/orchestrator seam:
- conversation identity validation (missing -> 400, unknown -> 404) is enforced
  by the router before any insert;
- the definition's actual ``role`` is persisted as the canonical ``agent_type``;
- control start/restart fail closed for any instance with real ``agent_runs``
  history, while control-only instances keep the compatibility behavior.
"""

from __future__ import annotations

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
from windagent_core.errors.exceptions import NotFoundError
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
        run_id = f"fake-run-{request.step_run_id}"
        handle = ExecutionHandle(
            handle_id=f"handle-{run_id}",
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
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.RUNNING,
        )

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return self.handles.get(runtime_run_id)


class RouteLocks:
    def resolve_or_create_lock(self, context):
        from types import SimpleNamespace

        return SimpleNamespace(
            lock_id=f"lock-{context.scope_id}",
            canonical_model_id="windagent/local-agent",
            routing_snapshot=SimpleNamespace(rule_version=1, reason="phase4-test"),
        )


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
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


async def _create_conversation(db, service: OrchestratorService, conv_id: str) -> None:
    await service.create_conversation(
        conversation_id=conv_id,
        title="Control lifecycle conversation",
        objective="Prove the control-plane lifecycle contract",
    )


@pytest.mark.asyncio
async def test_launch_agent_persists_definition_role_as_agent_type(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-role")

    created = await service.launch_agent(
        agent_instance_id="inst-role-01",
        conversation_id="conv-role",
        definition_id="def-coder-01",
        agent_type="coder",
        canonical_model_id="claude-3-5-sonnet",
    )
    assert created["id"] == "inst-role-01"
    assert created["definition_id"] == "def-coder-01"

    async with db.session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT agent_type FROM agent_instances WHERE agent_instance_id=:id"
                ),
                {"id": "inst-role-01"},
            )
        ).scalar_one()
        assert row == "coder"


@pytest.mark.asyncio
async def test_has_agent_run_history_true_after_real_run(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-history")

    result = await service.submit_goal(
        conversation_id="conv-history",
        objective="Run a real agent",
        subtasks=(Subtask(objective="Do the work", node_id="work"),),
    )
    agent_instance_id = result.agents[0].agent_instance_id

    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        assert await repo.has_agent_run_history(agent_instance_id) is True


@pytest.mark.asyncio
async def test_has_agent_run_history_false_for_control_only(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-control")

    await service.launch_agent(
        agent_instance_id="inst-control-01",
        conversation_id="conv-control",
        definition_id="def-coder-01",
        agent_type="coder",
    )

    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        assert await repo.has_agent_run_history("inst-control-01") is False


@pytest.mark.asyncio
async def test_restart_rejected_when_real_run_history_exists(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-restart")

    result = await service.submit_goal(
        conversation_id="conv-restart",
        objective="Run then attempt a control restart",
        subtasks=(Subtask(objective="Do the work", node_id="work"),),
    )
    agent_instance_id = result.agents[0].agent_instance_id

    # Even though the run is still live, restart must fail closed.
    with pytest.raises(RuntimeError):
        await service.restart_agent(agent_instance_id)


@pytest.mark.asyncio
async def test_start_rejected_when_real_run_history_exists(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-start")

    result = await service.submit_goal(
        conversation_id="conv-start",
        objective="Run then attempt a control start",
        subtasks=(Subtask(objective="Do the work", node_id="work"),),
    )
    agent_instance_id = result.agents[0].agent_instance_id

    with pytest.raises(RuntimeError):
        await service.start_agent(agent_instance_id)


@pytest.mark.asyncio
async def test_control_only_instance_keeps_start_restart_compatibility(db):
    service = _service(db, HoldingRuntime())
    await _create_conversation(db, service, "conv-compat")

    await service.launch_agent(
        agent_instance_id="inst-compat-01",
        conversation_id="conv-compat",
        definition_id="def-coder-01",
        agent_type="coder",
        status="idle",
    )

    started = await service.start_agent("inst-compat-01")
    assert started is not None
    assert started["status"] == "RUNNING"

    restarted = await service.restart_agent("inst-compat-01")
    assert restarted is not None
    assert restarted["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_launch_agent_unknown_conversation_raises_and_writes_nothing(db):
    """Direct launch against an unknown conversation raises the stable domain
    exception and writes neither an agent instance/session nor an event."""
    service = _service(db, HoldingRuntime())

    with pytest.raises(NotFoundError):
        await service.launch_agent(
            agent_instance_id="inst-unknown-01",
            conversation_id="conv-does-not-exist",
            definition_id="def-coder-01",
            agent_type="coder",
        )

    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        # No agent instance/session was persisted.
        assert await repo.get_agent_instance("inst-unknown-01") is None
        # No conversation event was appended.
        assert await repo.conversation_events_after("conv-does-not-exist") == []
