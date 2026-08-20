"""Phase 6 acceptance tests: conversation replay, audit-only streams, recovery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_orchestration.orchestrator_service import OrchestratorService
from windagent_orchestration.recovery.manager import RecoveryManager
from windagent_api.routers.conversation_streams import router as conversation_streams_router
from windagent_api.services.realtime_hub import RealtimeHub
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.realtime.sql_replay import SqlRealtimeReplayAdapter
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase6.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_conversation_socket_replays_multiplexed_agent_events_with_cursor(db):
    conversation_id = "phase6-conversation"
    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        await repo.ensure_conversation(conversation_id)
        for event_id, agent_id, session_id, output in (
            ("event-a", "agent-a", "session-a", "A"),
            ("event-b", "agent-b", "session-b", "B"),
            ("event-c", "agent-c", "session-c", "C"),
        ):
            await repo.append_event(
                event_id=event_id,
                idempotency_key=f"idempotency-{event_id}",
                conversation_id=conversation_id,
                agent_instance_id=agent_id,
                agent_session_id=session_id,
                event_type="terminal_output",
                data={"output": output},
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
            events = [socket.receive_json() for _ in range(3)]
        with client.websocket_connect(
            f"/ws/conversations/{conversation_id}?after_sequence=2"
        ) as socket:
            replay = socket.receive_json()

    assert [event["data"]["output"] for event in events] == ["A", "B", "C"]
    assert [event["agent_instance_id"] for event in events] == ["agent-a", "agent-b", "agent-c"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert all(event["event_id"] and event["idempotency_key"] for event in events)
    assert all(event["is_replay"] is True for event in events)
    assert replay["data"]["output"] == "C"
    assert replay["agent_instance_id"] == "agent-c"
    assert replay["sequence"] == 3


@pytest.mark.asyncio
async def test_interrupted_stream_creates_audit_only_partial_artifact(db):
    conversation_id = "phase6-partial"
    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        await repo.ensure_conversation(conversation_id)
        await session.commit()

    service = OrchestratorService(
        db.session_factory,
        ExecutionRuntimeRegistry(),
        repo_factory=lambda session: MultiAgentRepository(session),
    )

    async def interrupted_chunks():
        yield "safe first token "
        raise RuntimeError("provider stream disconnected")

    with pytest.raises(RuntimeError, match="disconnected"):
        async for _ in service.stream_agent_output(
            conversation_id=conversation_id,
            agent_instance_id="agent-unavailable",
            stream_id="stream-1",
            chunks=interrupted_chunks(),
        ):
            pass

    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        artifacts = await repo.partial_stream_artifacts(conversation_id)
        events = await repo.conversation_events_after(conversation_id)

    assert len(artifacts) == 1
    assert artifacts[0]["audit_only"] is True
    assert artifacts[0]["content_redacted"] == "safe first token "
    assert artifacts[0]["failure_reason"] == "provider stream disconnected"
    assert [event["event_type"] for event in events] == ["agent_stream_partial_audited"]
    assert all("safe first token" not in str(event["data"]) for event in events)


@pytest.mark.asyncio
async def test_production_recovery_runs_in_durable_order(db):
    calls: list[str] = []

    class OrderedOrchestrator:
        async def reattach_live_runs(self, **kwargs):
            assert kwargs == {"reconcile_worktrees": False, "resume_scheduler": False}
            calls.append("runtime")
            return SimpleNamespace(
                reattached_agent_run_ids=("run-live",), orphaned_agent_run_ids=("run-orphan",)
            )

        async def reconcile_runtime_completions(self):
            calls.append("dag-completions")
            return ("run-completed",)

        async def schedule_due_nodes(self):
            calls.append("dag-schedule")
            return ("run-dispatched",)

        async def reconcile_route_locks(self):
            calls.append("route-locks")
            return ("route-lock-1",)

        async def reconcile_worktrees(self):
            calls.append("worktrees")
            return SimpleNamespace(
                reattached_worktree_ids=("worktree-live",), cleaned_worktree_ids=("worktree-orphan",)
            )

    async def publish_pending_approvals() -> int:
        calls.append("pending-approvals")
        return 2

    report = await RecoveryManager(
        lambda: SqlUnitOfWork(db.session_factory), instance_id="phase6-recovery"
    ).recover_production(
        OrderedOrchestrator(), publish_pending_approvals=publish_pending_approvals
    )

    assert report.leader_acquired is True
    assert calls == [
        "runtime",
        "dag-completions",
        "dag-schedule",
        "route-locks",
        "worktrees",
        "pending-approvals",
    ]
    assert report.reattached_agent_run_ids == ("run-live",)
    assert report.orphaned_agent_run_ids == ("run-orphan",)
    assert report.route_lock_ids == ("route-lock-1",)
    assert report.reconciled_worktree_ids == ("worktree-live", "worktree-orphan")
    assert report.published_approval_count == 2
