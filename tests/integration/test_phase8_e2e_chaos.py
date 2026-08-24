"""Phase 8 production-boundary acceptance scenarios (G9.7).

The only doubles are the external Hermes and provider boundaries.  Every test
uses the real orchestration service, SQL repositories, scheduler, recovery
manager, worktree manager, provider coordinator, or WebSocket router.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.fakes.execution.controlled_runtime import (
    ControlledHermesRuntime,
    ScriptedProviderAdapter,
)
from tests.fakes.providers.provider_graph import PersistentRouteLocks, seed_provider_graph
from windagent_api.routers.conversation_streams import router as conversation_streams_router
from windagent_api.services.realtime_hub import RealtimeHub
from windagent_core.contracts.providers.responses import ProviderResponse, ProviderUsage
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_execution.worktree.context import WorktreeContextManager
from windagent_orchestration.orchestrator_service import OrchestratorService, Subtask
from windagent_orchestration.recovery.manager import RecoveryManager
from windagent_providers.base.errors import RateLimitFailure
from windagent_providers.routing.circuit_breaker import InMemoryEndpointStateManager
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.memory_ports import (
    InMemoryEndpointRegistry,
    InMemoryQuotaStateManager,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.database.sync_factory import make_sync_session_factory
from windagent_storage.orm.models import BaseORM
from windagent_storage.realtime.sql_replay import SqlRealtimeReplayAdapter
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_storage.repositories.v3_repositories import SQLRouteAttemptRepository
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
pytestmark = pytest.mark.postgres



def _stable_route_locks(
    db: DatabaseManager,
    canonical_model_id: str = "phase8/local-agent@2026-08-03",
) -> PersistentRouteLocks:
    """A deterministic route-lock boundary that persists locks for FK enforcement."""
    return PersistentRouteLocks(
        make_sync_session_factory(db.db_url),
        canonical_model_id=canonical_model_id,
        rule_id="phase8-integration",
        rule_version=1,
        reason="controlled external boundary",
    )


@pytest.fixture
async def db(tmp_path: Path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase8.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


def _service(
    db: DatabaseManager,
    runtime: ControlledHermesRuntime,
    *,
    route_locks: PersistentRouteLocks | None = None,
    provider_coordinator: EndpointExecutionCoordinator | None = None,
    worktrees: WorktreeContextManager | None = None,
) -> OrchestratorService:
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("local_agent", runtime)
    return OrchestratorService(
        db.session_factory,
        registry,
        route_locks or _stable_route_locks(db),
        provider_coordinator,
        worktrees,
        repo_factory=lambda session: MultiAgentRepository(session),
    )


def _agent(agents: Any, node: str) -> Any:
    return next(agent for agent in agents if agent.node_id.endswith(f":{node}"))


async def _live_agents(service: OrchestratorService, conversation_id: str) -> dict[str, dict[str, Any]]:
    return {
        str(agent["agent_instance_id"]): agent
        for agent in await service.list_agents(conversation_id)
    }


def _runtime_run_for_agent_run(runtime: ControlledHermesRuntime, agent_run_id: str) -> str:
    return next(
        runtime_run_id
        for runtime_run_id, handle in reversed(list(runtime.handles.items()))
        if handle.attempt_id == agent_run_id
    )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_e2e_parent_dag_event_isolation_fanout_fanin_concurrency_and_stop_race(
    db: DatabaseManager,
):
    runtime = ControlledHermesRuntime()
    service = _service(db, runtime)
    goal = await service.submit_goal(
        conversation_id="phase8-dag",
        objective="Run a production-shaped plan",
        subtasks=(
            Subtask(objective="Research the baseline", node_id="root"),
            Subtask(objective="Check an independent boundary", node_id="side"),
            Subtask(objective="Validate first fan-out", node_id="left", depends_on=("root",)),
            Subtask(objective="Validate second fan-out", node_id="right", depends_on=("root",)),
            Subtask(objective="Publish fan-in", node_id="join", depends_on=("left", "right")),
        ),
    )
    root, side, left, right, join = (
        _agent(goal.agents, node) for node in ("root", "side", "left", "right", "join")
    )
    assert root.status == side.status == "running"
    assert {left.status, right.status, join.status} == {"queued"}
    assert len({root.agent_instance_id, side.agent_instance_id}) == 2
    assert len({root.agent_session_id, side.agent_session_id}) == 2

    async with db.session_factory() as session:
        events = await MultiAgentRepository(session).conversation_events_after(goal.conversation_id)
    started = [event for event in events if event["event_type"] == "agent_run_started"]
    assert {event["agent_instance_id"] for event in started} == {
        root.agent_instance_id,
        side.agent_instance_id,
    }

    runtime.complete(root.runtime_run_id, {"root": "done"})
    assert await service.reconcile_runtime_completions() == (root.agent_run_id,)
    live = await _live_agents(service, goal.conversation_id)
    left, right = live[left.agent_instance_id], live[right.agent_instance_id]
    assert left["status"] == right["status"] == "running"

    runtime.complete(_runtime_run_for_agent_run(runtime, str(left["agent_run_id"])), {"left": "done"})
    runtime.complete(_runtime_run_for_agent_run(runtime, str(right["agent_run_id"])), {"right": "done"})
    await service.reconcile_runtime_completions()
    live = await _live_agents(service, goal.conversation_id)
    join = live[join.agent_instance_id]
    assert join["status"] == "running"

    runtime.complete(_runtime_run_for_agent_run(runtime, str(join["agent_run_id"])), {"join": "done"})
    runtime.complete(side.runtime_run_id, {"side": "done"})
    await service.reconcile_runtime_completions()
    async with db.session_factory() as session:
        parent_state = await session.scalar(
            text("SELECT status FROM parent_tasks WHERE parent_task_id=:id"),
            {"id": goal.parent_task_id},
        )
    assert parent_state == "completed"

    grouped = await service.submit_goal(
        conversation_id="phase8-concurrency",
        objective="Serialize a shared external resource",
        subtasks=(
            Subtask(objective="First group operation", node_id="first", concurrency_group="shared"),
            Subtask(objective="Second group operation", node_id="second", concurrency_group="shared"),
        ),
    )
    first, second = (_agent(grouped.agents, node) for node in ("first", "second"))
    assert [agent.status for agent in (first, second)].count("running") == 1
    running = first if first.status == "running" else second
    waiting = second if running is first else first
    runtime.complete(running.runtime_run_id)
    await service.reconcile_runtime_completions()
    live = await _live_agents(service, grouped.conversation_id)
    assert live[waiting.agent_instance_id]["status"] == "running"

    raced = await service.submit_goal(
        conversation_id="phase8-stop-race",
        objective="Stop must win over a late completion",
        subtasks=(Subtask(objective="Long running operation", node_id="run"),),
    )
    agent = raced.agents[0]
    assert await service.stop_agent(agent.agent_instance_id, conversation_id=raced.conversation_id)
    late = await service.complete_agent_node(
        conversation_id=raced.conversation_id,
        agent_instance_id=agent.agent_instance_id,
        succeeded=True,
        result={"late": True},
    )
    assert late.applied is False
    assert agent.runtime_run_id in runtime.cancelled


@pytest.mark.asyncio
async def test_e2e_retry_storm_stops_at_durable_attempt_cap(db: DatabaseManager):
    runtime = ControlledHermesRuntime()
    service = _service(db, runtime)
    goal = await service.submit_goal(
        conversation_id="phase8-retry-storm",
        objective="Bound repeated runtime failures",
        subtasks=(Subtask(objective="Run an unreliable external operation", node_id="retry"),),
    )
    agent = goal.agents[0]

    for attempt in range(1, 4):
        runtime.fail(_runtime_run_for_agent_run(runtime, agent.agent_run_id), f"failure {attempt}")
        assert await service.reconcile_runtime_completions() == (agent.agent_run_id,)
        if attempt < 3:
            async with db.session_factory() as session:
                await session.execute(
                    text(
                        "UPDATE task_node_runs SET next_retry_at=:past "
                        "WHERE task_node_run_id=(SELECT task_node_run_id FROM agent_runs "
                        "WHERE agent_run_id=:agent_run_id)"
                    ),
                    {"past": "2000-01-01 00:00:00", "agent_run_id": agent.agent_run_id},
                )
                await session.commit()
            assert [launch.agent_run_id for launch in await service.schedule_due_nodes(goal.parent_task_id)] == [
                agent.agent_run_id
            ]

    async with db.session_factory() as session:
        node = await session.execute(
            text(
                "SELECT tnr.state, tnr.retry_state_json FROM task_node_runs tnr "
                "JOIN agent_runs ar ON ar.task_node_run_id=tnr.task_node_run_id "
                "WHERE ar.agent_run_id=:agent_run_id"
            ),
            {"agent_run_id": agent.agent_run_id},
        )
    state, retry_state = node.one()
    assert state == "failed"
    assert '"attempt": 3' in retry_state
    assert len(runtime.requests) == 3


@pytest.mark.asyncio
async def test_e2e_same_model_failover_and_partial_stream_are_durable(db: DatabaseManager):
    canonical_model_id = "phase8/model@2026-08-03"
    rate_limited = ScriptedProviderAdapter(
        [RateLimitFailure("scripted 429", provider_id="provider-a", status_code=429)]
    )
    successful = ScriptedProviderAdapter(
        [
            ProviderResponse(
                canonical_model_id="must-be-overridden-by-route-lock",
                provider_model_id="exact-revision",
                endpoint_id="provider-b-endpoint",
                text="answer from provider B",
                usage=ProviderUsage(prompt_tokens=3, completion_tokens=2),
            )
        ]
    )
    bindings = [
        {
            "endpoint_id": "provider-a-endpoint",
            "binding_id": "binding-a",
            "canonical_model_id": canonical_model_id,
            "provider_model_id": "exact-revision",
            "provider_name": "provider-a",
            "base_url": "https://provider-a.invalid/v1",
            "credential_ciphertext": "enc:v1:fake-a",
            "equivalence_level": "exact_revision",
            "is_active": True,
        },
        {
            "endpoint_id": "provider-b-endpoint",
            "binding_id": "binding-b",
            "canonical_model_id": canonical_model_id,
            "provider_model_id": "exact-revision",
            "provider_name": "provider-b",
            "base_url": "https://provider-b.invalid/v1",
            "credential_ciphertext": "enc:v1:fake-b",
            "equivalence_level": "exact_revision",
            "is_active": True,
        },
    ]
    endpoint_state = InMemoryEndpointStateManager()
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: rate_limited
        if candidate.endpoint_id == "provider-a-endpoint"
        else successful,
        endpoint_registry=InMemoryEndpointRegistry(bindings),
        endpoint_state=endpoint_state,
        quota_state=InMemoryQuotaStateManager(),
        attempt_log=SQLRouteAttemptRepository(make_sync_session_factory(db.db_url)()),
    )
    # GAP A: FK enforcement needs the provider reference graph seeded before
    # agent_turns/route_attempts reference it.
    seed_provider_graph(
        make_sync_session_factory(db.db_url)(),
        canonical_model_id=canonical_model_id,
        bindings=bindings,
    )
    runtime = ControlledHermesRuntime()
    service = _service(
        db,
        runtime,
        route_locks=_stable_route_locks(db, canonical_model_id),
        provider_coordinator=coordinator,
    )
    goal = await service.submit_goal(
        conversation_id="phase8-provider",
        objective="Run a routed external turn",
        subtasks=(Subtask(objective="Answer the user", node_id="answer"),),
    )
    agent = goal.agents[0]
    turn = await service.execute_provider_turn(
        conversation_id=goal.conversation_id,
        agent_instance_id=agent.agent_instance_id,
        prompt="hello",
    )
    audit = await service.routing_turn_detail(goal.conversation_id, turn.turn_id)
    assert turn.canonical_model_id == canonical_model_id
    assert turn.text == "answer from provider B"
    assert rate_limited.calls == successful.calls == 1
    assert [(attempt["status"], attempt["provider_binding_id"]) for attempt in audit["attempts"]] == [
        ("rate_limited", "binding-a"),
        ("success", "binding-b"),
    ]
    assert await endpoint_state.is_available("provider-a-endpoint") is False

    async def interrupted_chunks():
        yield "incomplete output that must not enter the transcript"
        raise RuntimeError("scripted provider stream crash")

    with pytest.raises(RuntimeError, match="stream crash"):
        async for _ in service.stream_agent_output(
            conversation_id=goal.conversation_id,
            agent_instance_id=agent.agent_instance_id,
            stream_id="phase8-stream",
            chunks=interrupted_chunks(),
        ):
            pass
    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        artifacts = await repo.partial_stream_artifacts(goal.conversation_id)
        events = await repo.conversation_events_after(goal.conversation_id)
    assert len(artifacts) == 1 and artifacts[0]["audit_only"] is True
    assert artifacts[0]["content_redacted"] == "incomplete output that must not enter the transcript"
    assert all(
        "incomplete output" not in str(event["data"])
        for event in events
        if event["event_type"] == "agent_stream_partial_audited"
    )


@pytest.mark.asyncio
async def test_e2e_coding_worktree_isolation_and_cancel_cleanup(
    db: DatabaseManager, tmp_path: Path
):
    repository = tmp_path / "primary"
    _git(tmp_path, "init", str(repository))
    _git(repository, "config", "user.email", "phase8@example.test")
    _git(repository, "config", "user.name", "Phase 8")
    (repository / "README.md").write_text("base\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "initial")

    runtime = ControlledHermesRuntime()
    worktrees = WorktreeContextManager(
        repository,
        worktree_root=tmp_path / "linked-worktrees",
        quarantine_root=tmp_path / "quarantine",
    )
    service = _service(db, runtime, worktrees=worktrees)
    goal = await service.submit_goal(
        conversation_id="phase8-worktree",
        objective="Run two isolated coding agents",
        subtasks=(
            Subtask(objective="Implement the first change", node_id="left"),
            Subtask(objective="Fix the second change", node_id="right"),
        ),
    )
    left, right = (_agent(goal.agents, node) for node in ("left", "right"))
    async with db.session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT agent_instance_id, path, branch FROM worktrees ORDER BY agent_instance_id")
            )
        ).mappings().all()
    assert len(rows) == 2
    assert len({row["path"] for row in rows}) == len({row["branch"] for row in rows}) == 2
    assert all(Path(row["path"]).resolve() != repository.resolve() for row in rows)
    assert _git(repository, "status", "--porcelain").stdout == ""

    requests = {request.attempt_id: request for request in runtime.requests}
    assert Path(requests[left.agent_run_id].context["workspace_root"]).is_dir()
    assert Path(requests[right.agent_run_id].context["workspace_root"]).is_dir()
    left_row = next(row for row in rows if row["agent_instance_id"] == left.agent_instance_id)
    (Path(left_row["path"]) / "uncommitted.txt").write_text("keep for audit\n", encoding="utf-8")
    assert await service.stop_agent(left.agent_instance_id, conversation_id=goal.conversation_id)
    assert left.runtime_run_id in runtime.cancelled
    assert not worktrees.is_registered(left_row["path"])
    assert worktrees.is_registered(next(row["path"] for row in rows if row["agent_instance_id"] == right.agent_instance_id))
    assert _git(
        repository,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{left_row['branch']}",
        check=False,
    ).returncode == 1
    assert _git(repository, "status", "--porcelain").stdout == ""


@pytest.mark.asyncio
async def test_e2e_restart_mid_dag_surfaces_approval_and_unavailable_runtime(db: DatabaseManager):
    runtime = ControlledHermesRuntime()
    route_locks = _stable_route_locks(db)
    first = _service(db, runtime, route_locks=route_locks)
    goal = await first.submit_goal(
        conversation_id="phase8-recovery",
        objective="Recover a partially executed plan",
        subtasks=(
            Subtask(objective="Research the recoverable step", node_id="root"),
            Subtask(objective="Check abandoned runtime", node_id="orphan"),
            Subtask(objective="Validate after recovery", node_id="after", depends_on=("root",)),
        ),
    )
    root, orphan, after = (_agent(goal.agents, node) for node in ("root", "orphan", "after"))
    runtime.complete(root.runtime_run_id, {"checkpoint": "durable"})
    runtime.crash(orphan.runtime_run_id)

    approval_calls: list[str] = []

    async def publish_pending_approvals() -> int:
        approval_calls.append("published")
        return 1

    restarted = _service(db, runtime, route_locks=route_locks)
    report = await RecoveryManager(
        lambda: SqlUnitOfWork(db.session_factory),
        instance_id="phase8-recovery",
    ).recover_production(restarted, publish_pending_approvals=publish_pending_approvals)
    assert root.agent_run_id in report.reattached_agent_run_ids
    assert orphan.agent_run_id in report.unavailable_agent_run_ids
    assert report.completed_ingested_count == 1
    assert report.published_approval_count == 1 and approval_calls == ["published"]
    live = await _live_agents(restarted, goal.conversation_id)
    assert live[after.agent_instance_id]["status"] == "running"
    assert live[orphan.agent_instance_id]["status"] == "running"


@pytest.mark.asyncio
async def test_e2e_socket_reconnect_replays_only_missed_events(db: DatabaseManager):
    conversation_id = "phase8-socket"
    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        await repo.ensure_conversation(conversation_id)
        for event_id, agent_id, payload in (
            ("phase8-event-a", "agent-a", "A"),
            ("phase8-event-b", "agent-b", "B"),
        ):
            await repo.append_event(
                event_id=event_id,
                idempotency_key=f"idempotency-{event_id}",
                conversation_id=conversation_id,
                agent_instance_id=agent_id,
                agent_session_id=f"session-{agent_id}",
                event_type="terminal_output",
                data={"output": payload},
            )
        await session.commit()

    app = FastAPI()
    app.include_router(conversation_streams_router)
    app.state.container = SimpleNamespace(
        db=db,
        realtime_hub=RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory)),
    )
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}") as socket:
            first = socket.receive_json()
        with client.websocket_connect(
            f"/ws/conversations/{conversation_id}?after_sequence={first['sequence']}"
        ) as socket:
            missed = socket.receive_json()

    assert (first["event_id"], first["agent_instance_id"], first["sequence"]) == (
        "phase8-event-a",
        "agent-a",
        1,
    )
    assert (missed["event_id"], missed["agent_instance_id"], missed["sequence"]) == (
        "phase8-event-b",
        "agent-b",
        2,
    )
    assert missed["event_id"] != first["event_id"]