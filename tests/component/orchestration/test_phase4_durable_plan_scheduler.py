"""Phase 4 acceptance tests for the durable immutable-plan scheduler."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
    ExecutionRuntimePort,
    RuntimeStatus,
    RuntimeStatusEnum,
)
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_orchestration.orchestrator_service import (
    OrchestratorService,
    PlanRevisionConflict,
    Subtask,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


class HoldingRuntime(ExecutionRuntimePort):
    def __init__(self) -> None:
        self.handles: dict[str, ExecutionHandle] = {}
        self.cancelled: list[str] = []

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        handle = ExecutionHandle(
            handle_id=f"handle-{uuid.uuid4().hex}",
            runtime_run_id=f"runtime-{uuid.uuid4().hex}",
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )
        self.handles[handle.runtime_run_id] = handle
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
            routing_snapshot=SimpleNamespace(
                rule_id="phase4-test",
                rule_version=1,
                reason="durable plan scheduler test",
            ),
        )


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase4.db'}")
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


def _by_suffix(agents, suffix: str):
    return next(agent for agent in agents if agent.node_id.endswith(f":{suffix}"))


@pytest.mark.asyncio
async def test_pinned_dag_fanout_fanin_and_retry_are_durable(db: DatabaseManager):
    runtime = HoldingRuntime()
    service = _service(db, runtime)
    goal = await service.submit_goal(
        conversation_id="phase4-dag",
        objective="Run a pinned DAG",
        subtasks=(
            Subtask(objective="A", node_id="a"),
            Subtask(objective="B", node_id="b", depends_on=("a",)),
            Subtask(objective="C", node_id="c", depends_on=("a",)),
            Subtask(objective="D", node_id="d", depends_on=("b", "c")),
        ),
    )
    a, b, c, d = (_by_suffix(goal.agents, node) for node in ("a", "b", "c", "d"))
    assert a.status == "running"
    assert {b.status, c.status, d.status} == {"queued"}

    after_a = await service.complete_agent_node(
        conversation_id=goal.conversation_id,
        agent_instance_id=a.agent_instance_id,
        succeeded=True,
        result={"ok": True},
    )
    assert set(after_a.dispatched_agent_run_ids) == {b.agent_run_id, c.agent_run_id}

    after_b = await service.complete_agent_node(
        conversation_id=goal.conversation_id,
        agent_instance_id=b.agent_instance_id,
        succeeded=True,
    )
    assert not after_b.dispatched_agent_run_ids
    after_c = await service.complete_agent_node(
        conversation_id=goal.conversation_id,
        agent_instance_id=c.agent_instance_id,
        succeeded=True,
    )
    assert after_c.dispatched_agent_run_ids == (d.agent_run_id,)
    assert (await service.complete_agent_node(
        conversation_id=goal.conversation_id,
        agent_instance_id=d.agent_instance_id,
        succeeded=True,
    )).state == "completed"

    retry_goal = await service.submit_goal(
        conversation_id="phase4-retry",
        objective="Retry a node",
        subtasks=(Subtask(objective="retry", node_id="retry"),),
    )
    retry_agent = retry_goal.agents[0]
    retry = await service.complete_agent_node(
        conversation_id=retry_goal.conversation_id,
        agent_instance_id=retry_agent.agent_instance_id,
        succeeded=False,
        error="transient",
    )
    assert retry.state == "retry_wait" and retry.next_retry_at
    async with db.session_factory() as session:
        await session.execute(
            text("UPDATE task_node_runs SET next_retry_at=:past WHERE task_node_run_id=(SELECT task_node_run_id FROM agent_runs WHERE agent_run_id=:agent_run_id)"),
            {"past": "2000-01-01 00:00:00", "agent_run_id": retry_agent.agent_run_id},
        )
        await session.commit()
    rescheduled = await service.schedule_due_nodes(retry_goal.parent_task_id)
    assert [item.agent_run_id for item in rescheduled] == [retry_agent.agent_run_id]

    async with db.session_factory() as session:
        assert (await session.execute(text("SELECT status FROM parent_tasks WHERE parent_task_id=:id"), {"id": goal.parent_task_id})).scalar_one() == "completed"
        assert (await session.execute(text("SELECT COUNT(*) FROM task_node_runs WHERE parent_task_id=:id AND state='completed'"), {"id": goal.parent_task_id})).scalar_one() == 4


@pytest.mark.asyncio
async def test_revising_a_running_plan_appends_a_snapshot_and_preserves_live_runs(
    db: DatabaseManager,
):
    runtime = HoldingRuntime()
    service = _service(db, runtime)
    goal = await service.submit_goal(
        conversation_id="phase4-plan-revision",
        objective="Keep an audit history while the first task runs",
        subtasks=(
            Subtask(objective="Original running task", node_id="original"),
            Subtask(objective="Original dependent task", node_id="dependent", depends_on=("original",)),
        ),
    )
    original = _by_suffix(goal.agents, "original")
    assert original.status == "running"

    revision = await service.revise_plan(
        conversation_id=goal.conversation_id,
        parent_task_id=goal.parent_task_id,
        base_plan_version_id=goal.plan_version_id,
        subtasks=(
            Subtask(objective="Replacement task", node_id="replacement"),
            Subtask(objective="New follow-up", node_id="follow_up", depends_on=("replacement",)),
        ),
    )
    assert revision.version == 2
    assert revision.plan_version_id != goal.plan_version_id

    history = await service.list_plan_versions(
        conversation_id=goal.conversation_id,
        parent_task_id=goal.parent_task_id,
    )
    assert [item["version"] for item in history] == [1, 2]
    assert [node["objective"] for node in history[0]["dag"]["nodes"]] == [
        "Original running task", "Original dependent task"
    ]
    assert [node["objective"] for node in history[1]["dag"]["nodes"]] == [
        "Replacement task", "New follow-up"
    ]
    assert history[0]["is_active"] is False
    assert history[1]["is_active"] is True

    active_graph = (await service.list_task_graphs(goal.conversation_id))[0]
    assert active_graph["plan_version_id"] == revision.plan_version_id
    async with db.session_factory() as session:
        live_plan_id = (
            await session.execute(
                text(
                    "SELECT plan_version_id FROM agent_runs WHERE agent_run_id=:agent_run_id"
                ),
                {"agent_run_id": original.agent_run_id},
            )
        ).scalar_one()
    assert live_plan_id == goal.plan_version_id

    with pytest.raises(PlanRevisionConflict):
        await service.revise_plan(
            conversation_id=goal.conversation_id,
            parent_task_id=goal.parent_task_id,
            base_plan_version_id=goal.plan_version_id,
            subtasks=(Subtask(objective="Stale editor", node_id="stale"),),
        )


@pytest.mark.asyncio
async def test_concurrency_lock_cancel_precedence_and_tool_idempotency(db: DatabaseManager):
    runtime = HoldingRuntime()
    service = _service(db, runtime)
    grouped = await service.submit_goal(
        conversation_id="phase4-group",
        objective="Serialize coding worktree",
        subtasks=(
            Subtask(objective="left", node_id="left", concurrency_group="worktree:one"),
            Subtask(objective="right", node_id="right", concurrency_group="worktree:one"),
        ),
    )
    left, right = (_by_suffix(grouped.agents, node) for node in ("left", "right"))
    assert left.status == "running" and right.status == "queued"
    unlocked = await service.complete_agent_node(
        conversation_id=grouped.conversation_id,
        agent_instance_id=left.agent_instance_id,
        succeeded=True,
    )
    assert unlocked.dispatched_agent_run_ids == (right.agent_run_id,)

    cancelled_goal = await service.submit_goal(
        conversation_id="phase4-cancel",
        objective="Cancel before completion",
        subtasks=(Subtask(objective="cancel me", node_id="cancel"),),
    )
    cancelled = cancelled_goal.agents[0]
    stale = await service.complete_agent_node(
        conversation_id=cancelled_goal.conversation_id,
        agent_instance_id=cancelled.agent_instance_id,
        succeeded=True,
        fencing_token="stale-runtime-generation",
    )
    assert stale.applied is False
    assert await service.stop_agent(cancelled.agent_instance_id, conversation_id=cancelled_goal.conversation_id)
    late = await service.complete_agent_node(
        conversation_id=cancelled_goal.conversation_id,
        agent_instance_id=cancelled.agent_instance_id,
        succeeded=True,
    )
    assert late.applied is False

    calls: list[str] = []

    async def side_effect():
        calls.append("ran")
        return {"ok": True}, "artifact://tool-result"

    first = await service.execute_idempotent_tool(
        agent_instance_id=right.agent_instance_id,
        tool_name="write_file",
        idempotency_key="phase4-tool-key",
        arguments={"path": "safe.txt", "api_key": "not persisted"},
        operation=side_effect,
    )
    duplicate = await service.execute_idempotent_tool(
        agent_instance_id=right.agent_instance_id,
        tool_name="write_file",
        idempotency_key="phase4-tool-key",
        arguments={"path": "safe.txt"},
        operation=side_effect,
    )
    assert first.executed is True and first.status == "completed"
    assert duplicate.executed is False and duplicate.result_ref == "artifact://tool-result"
    assert calls == ["ran"]
