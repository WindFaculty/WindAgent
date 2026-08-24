"""Phase 5 acceptance tests for Git-backed coding-agent worktree lifecycle."""

from __future__ import annotations

from pathlib import Path
import subprocess
import uuid

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
from windagent_execution.worktree.context import WorktreeContextManager
from windagent_orchestration.orchestrator_service import OrchestratorService, Subtask
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


class HoldingRuntime(ExecutionRuntimePort):
    def __init__(self) -> None:
        self.handles: dict[str, ExecutionHandle] = {}
        self.cancelled: list[str] = []
        self.requests: list[ExecutionRequest] = []

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        self.requests.append(request)
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
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.RUNNING,
        )

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return self.handles.get(runtime_run_id)


class RouteLocks:
    def resolve_or_create_lock(self, context):
        return type(
            "RouteLock",
            (),
            {
                "lock_id": f"lock-{context.scope_id}",
                "canonical_model_id": "windagent/local-agent",
                "routing_snapshot": type(
                    "Snapshot", (), {"rule_version": 1, "rule_id": "phase5", "reason": "test"}
                )(),
            },
        )()


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "primary"
    _git(tmp_path, "init", str(repo))
    _git(repo, "config", "user.email", "phase5@example.test")
    _git(repo, "config", "user.name", "Phase 5 Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
async def db(tmp_path: Path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase5.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


def _service(
    db: DatabaseManager, runtime: HoldingRuntime, worktrees: WorktreeContextManager
) -> OrchestratorService:
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("local_agent", runtime)
    return OrchestratorService(
        db.session_factory,
        registry,
        RouteLocks(),
        worktree_manager=worktrees,
        repo_factory=lambda session: MultiAgentRepository(session),
    )


def _agent_by_node(agents, suffix: str):
    return next(agent for agent in agents if agent.node_id.endswith(f":{suffix}"))


@pytest.mark.asyncio
async def test_coding_agents_get_distinct_git_worktrees_and_cancel_quarantines_output(
    db: DatabaseManager, repository: Path, tmp_path: Path
):
    runtime = HoldingRuntime()
    worktrees = WorktreeContextManager(
        repository,
        worktree_root=tmp_path / "linked-worktrees",
        quarantine_root=tmp_path / "quarantine",
    )
    service = _service(db, runtime, worktrees)

    goal = await service.submit_goal(
        conversation_id="phase5-isolation",
        objective="Run isolated agent work",
        subtasks=(
            Subtask(objective="Implement the first code change", node_id="left"),
            Subtask(objective="Fix the second code path", node_id="right"),
            Subtask(objective="Research the existing API", node_id="research"),
            Subtask(objective="Use browser to inspect documentation", node_id="browser"),
        ),
    )
    left = _agent_by_node(goal.agents, "left")
    right = _agent_by_node(goal.agents, "right")
    research = _agent_by_node(goal.agents, "research")
    browser = _agent_by_node(goal.agents, "browser")

    async with db.session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT agent_instance_id, path, branch, status
                    FROM worktrees ORDER BY agent_instance_id
                    """
                )
            )
        ).mappings().all()
    assert {row["agent_instance_id"] for row in rows} == {
        left.agent_instance_id,
        right.agent_instance_id,
    }
    assert len({row["path"] for row in rows}) == len({row["branch"] for row in rows}) == 2
    assert all(Path(row["path"]).resolve() != repository.resolve() for row in rows)
    assert len(worktrees.list_worktrees()) == 2

    requests = {request.attempt_id: request for request in runtime.requests}
    for agent in (left, right):
        request = requests[agent.agent_run_id]
        assert request.context["workspace_root"] == request.parameters["workspace_root"]
        assert Path(request.context["workspace_root"]).is_dir()
    assert "workspace_root" not in requests[research.agent_run_id].context
    assert "workspace_root" not in requests[browser.agent_run_id].context
    assert _git(repository, "status", "--porcelain").stdout == ""

    left_row = next(row for row in rows if row["agent_instance_id"] == left.agent_instance_id)
    (Path(left_row["path"]) / "agent-output.txt").write_text("preserve me\n", encoding="utf-8")
    assert await service.stop_agent(left.agent_instance_id, conversation_id=goal.conversation_id)

    assert runtime.cancelled == [left.runtime_run_id]
    assert not worktrees.is_registered(left_row["path"])
    assert worktrees.is_registered(next(row["path"] for row in rows if row["agent_instance_id"] == right.agent_instance_id))
    assert _git(repository, "show-ref", "--verify", "--quiet", f"refs/heads/{left_row['branch']}", check=False).returncode == 1
    assert _git(repository, "status", "--porcelain").stdout == ""

    async with db.session_factory() as session:
        cleanup_row = (
            await session.execute(
                text(
                    "SELECT status, quarantine_path FROM worktrees WHERE agent_instance_id=:id"
                ),
                {"id": left.agent_instance_id},
            )
        ).mappings().one()
    assert cleanup_row["status"] == "quarantined"
    quarantine_path = Path(cleanup_row["quarantine_path"])
    assert (quarantine_path / "untracked" / "agent-output.txt").read_text(encoding="utf-8") == "preserve me\n"


@pytest.mark.asyncio
async def test_boot_reconciles_live_worktree_and_removes_unrecorded_crash_orphan(
    db: DatabaseManager, repository: Path, tmp_path: Path
):
    runtime = HoldingRuntime()
    worktrees = WorktreeContextManager(repository, worktree_root=tmp_path / "linked-worktrees")
    service = _service(db, runtime, worktrees)
    goal = await service.submit_goal(
        conversation_id="phase5-recovery",
        objective="Recover coding work",
        subtasks=(Subtask(objective="Implement recoverable code", node_id="coding"),),
    )
    coding = goal.agents[0]
    durable = worktrees.list_worktrees()[0]
    crash_orphan = worktrees.create_worktree("crash-orphan", agent_instance_id="crash-orphan")

    restarted = _service(db, runtime, worktrees)
    report = await restarted.reattach_live_runs()

    assert report.reattached_agent_run_ids == (coding.agent_run_id,)
    assert report.reattached_worktree_ids == (durable.worktree_id,)
    assert restarted.live_agent_run_ids == frozenset({coding.agent_run_id})
    assert not worktrees.is_registered(crash_orphan.path)
    assert _git(repository, "show-ref", "--verify", "--quiet", f"refs/heads/{crash_orphan.branch}", check=False).returncode == 1
