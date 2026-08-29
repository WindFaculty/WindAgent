"""Conversation entry point and durable multi-session supervisor (Phase 2).

``OrchestratorService`` is deliberately the only service allowed to create
runtime AgentSessions.  It derives agent roles from a task description instead
of accepting a frontend-selected runtime role, persists every ownership edge,
and keeps a rebuildable in-memory registry of live handles.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence

from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionRuntimePort,
    RuntimeStatusEnum,
)
from windagent_core.contracts.providers.requests import ProviderRequest
from windagent_core.domain.lifecycle import utc_now
from windagent_core.errors.exceptions import NotFoundError
from windagent_core.security.redaction import redact_before_persist
from windagent_core.contracts.repositories.multi_agent_repository import MultiAgentRepositoryPort
from windagent_orchestration.durable_plan_scheduler import DurablePlanScheduler
from windagent_orchestration.release.rollout import MultiAgentReleasePolicy


# Canonical multi-agent runtime statuses -> existing V3 API enum strings.
# The mapping is explicit and symmetric; the API schema is never changed.
_CANONICAL_TO_API_STATUS: dict[str, str] = {
    "active": "ACTIVE",
    "running": "RUNNING",
    "dispatching": "RUNNING",
    "idle": "IDLE",
    "queued": "IDLE",
    "created": "IDLE",
    "completed": "TERMINATED",
    "failed": "TERMINATED",
    "cancelled": "TERMINATED",
}

_API_TO_CANONICAL_STATUS: dict[str, str] = {
    "ACTIVE": "active",
    "RUNNING": "running",
    "IDLE": "idle",
    "TERMINATED": "cancelled",
}


@dataclass(frozen=True)
class Subtask:
    """A user goal fragment; the service, not the client, selects its agent type."""

    objective: str
    node_id: str | None = None
    depends_on: tuple[str, ...] = ()
    concurrency_group: str | None = None


@dataclass(frozen=True)
class AgentLaunch:
    agent_instance_id: str
    agent_session_id: str
    agent_run_id: str
    node_id: str
    agent_type: str
    runtime_run_id: str | None
    status: str


@dataclass(frozen=True)
class OrchestrationResult:
    conversation_id: str
    orchestrator_instance_id: str
    orchestrator_session_id: str
    parent_task_id: str
    plan_version_id: str
    agents: tuple[AgentLaunch, ...]


@dataclass(frozen=True)
class PlanRevisionResult:
    """The append-only snapshot created by an edit to a running plan."""

    conversation_id: str
    parent_task_id: str
    base_plan_version_id: str
    plan_version_id: str
    version: int


class PlanRevisionConflict(ValueError):
    """The editor based its change on a plan that is no longer active."""


@dataclass(frozen=True)
class ReattachReport:
    reattached_agent_run_ids: tuple[str, ...] = ()
    orphaned_agent_run_ids: tuple[str, ...] = ()
    unavailable_agent_run_ids: tuple[str, ...] = ()
    reattached_worktree_ids: tuple[str, ...] = ()
    cleaned_worktree_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorktreeReconcileReport:
    """Result of comparing durable worktree rows with Git's linked checkouts."""

    reattached_worktree_ids: tuple[str, ...] = ()
    cleaned_worktree_ids: tuple[str, ...] = ()
    runtime_orphaned_agent_instance_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorktreeReference:
    """Minimal worktree data reconstructed from durable orchestration state.

    Execution owns the concrete worktree manager.  This value deliberately
    carries only the attributes required by that injected manager, so the
    orchestration layer does not import execution infrastructure.
    """

    worktree_id: str
    agent_instance_id: str
    path: Path
    branch: str
    repo_root: Path


@dataclass(frozen=True)
class AgentTurnResult:
    """The public, redacted result of one routed provider turn."""

    turn_id: str
    agent_instance_id: str
    agent_session_id: str
    agent_run_id: str
    canonical_model_id: str
    route_lock_id: str
    routing_snapshot: Mapping[str, Any]
    text: str | None
    finish_reason: str


@dataclass(frozen=True)
class NodeCompletionResult:
    applied: bool
    state: str | None = None
    next_retry_at: str | None = None
    dispatched_agent_run_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_execution_id: str
    executed: bool
    status: str
    result_ref: str | None = None


@dataclass
class _LiveRun:
    agent_instance_id: str
    agent_session_id: str
    agent_run_id: str
    handle: ExecutionHandle


class OrchestratorService:
    """Creates plans and supervises independent runtime sessions per node.

    Sole new Story orchestration authority (studio.contract/v0.1). Public
    behavior is stable; ``studio_run_extension`` is the Plan A seam that later
    Studio phases use to route Studio run commands through this service.
    """

    def __init__(
        self,
        session_factory: Any,
        execution_registry: ExecutionRuntimePort | None = None,
        route_lock_service: Any | None = None,
        provider_execution_coordinator: Any | None = None,
        worktree_manager: Any | None = None,
        release_policy: MultiAgentReleasePolicy | None = None,
        release_telemetry: Any | None = None,
        studio_run_extension: Any | None = None,
        repo_factory: Callable[[Any], MultiAgentRepositoryPort] | None = None,
        agent_budget_controller: Any | None = None,
        agent_loop_repo_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._session_factory = session_factory
        # Phase 7: the execution runtime port is optional.  The API composes
        # this service with no runtime (control-plane mode): dispatch/reattach/
        # cancel/poll methods fail closed or return queued results for Worker
        # pickup.  Worker composition and direct orchestration tests still pass
        # a real runtime.
        self._execution_registry = execution_registry
        self._route_lock_service = route_lock_service
        self._provider_execution_coordinator = provider_execution_coordinator
        # This is intentionally injected by a composition root.  No API payload
        # can choose a repository/path for a coding runtime.
        self._worktree_manager = worktree_manager
        self._release_policy = release_policy
        self._release_telemetry = release_telemetry
        # Extension seam for Studio run commands (Plan A A4). Inert until a
        # Studio phase wires it; existing callers never see it.
        self._studio_run_extension = studio_run_extension
        self._repo_factory = repo_factory
        self._plan_scheduler = DurablePlanScheduler(
            repo_factory=repo_factory, session_factory=session_factory
        )
        self._agent_budget_controller = agent_budget_controller
        self._agent_loop_repo_factory = agent_loop_repo_factory
        self._live_runs: dict[str, _LiveRun] = {}
        self._registry_lock = asyncio.Lock()

    @property
    def _has_runtime(self) -> bool:
        """True when a real execution runtime port is composed."""
        return self._execution_registry is not None

    def _repo(self, session: Any):
        if self._repo_factory is not None:
            return self._repo_factory(session)
        raise RuntimeError(
            "OrchestratorService requires a repo_factory (MultiAgentRepository factory) "
            "to be injected by a composition root."
        )

    def _budget_controller(self) -> Any | None:
        if self._agent_budget_controller is not None:
            return self._agent_budget_controller
        factory = self._agent_loop_repo_factory
        if factory is None:
            return None
        from windagent_orchestration.agent_loop.budget_controller import AgentBudgetController
        multi_factory = self._repo_factory
        return AgentBudgetController(session_factory=self._session_factory, repo_factory=factory, multi_repo_factory=multi_factory)

    async def submit_goal(
        self,
        *,
        conversation_id: str,
        objective: str,
        subtasks: Sequence[Subtask] = (),
        title: str | None = None,
        release_actor_id: str | None = None,
    ) -> OrchestrationResult:
        """Persist a parent task + immutable plan, then launch every plan node.

        Runtime dispatch intentionally occurs after the ownership rows are
        committed.  If the process dies between those two actions, recovery sees
        a ``dispatching`` AgentRun rather than losing the request.
        """
        objective = objective.strip()
        if not objective:
            raise ValueError("objective must not be empty")
        if self._release_policy is not None:
            self._release_policy.require_runtime_activation(release_actor_id)

        normalized = self._normalize_subtasks(objective, subtasks)
        parent_task_id = self._new_id()
        plan_version_id = self._new_id()
        orchestrator_instance_id = self._new_id()
        orchestrator_session_id = self._new_id()

        prepared, edges = self._prepare_plan(normalized, plan_version_id)

        launches: list[dict[str, Any]] = []
        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.ensure_conversation(conversation_id, title)
            orchestrator_instance_id, orchestrator_session_id, created = (
                await repo.get_or_create_orchestrator(
                    conversation_id, orchestrator_instance_id, orchestrator_session_id
                )
            )
            if created:
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=conversation_id,
                    event_type="orchestrator_session_created",
                    data={"agent_type": "orchestrator"},
                    agent_instance_id=orchestrator_instance_id,
                    agent_session_id=orchestrator_session_id,
                )
            await repo.create_parent_task(parent_task_id, conversation_id, objective)
            dag = {
                "nodes": [
                    {
                        "node_id": n["node_id"],
                        "objective": n["objective"],
                        "agent_type": n["agent_type"],
                        "concurrency_group": n["concurrency_group"],
                    }
                    for n in prepared
                ],
                "edges": edges,
            }
            await repo.create_plan(plan_version_id, parent_task_id, dag)
            await repo.create_nodes_and_edges(plan_version_id, prepared, edges)
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="task_plan_created",
                data={"parent_task_id": parent_task_id, "plan_version_id": plan_version_id},
            )

            for node in prepared:
                launch = {
                    "agent_instance_id": self._new_id(),
                    "agent_session_id": self._new_id(),
                    "agent_run_id": self._new_id(),
                    "task_node_run_id": self._new_id(),
                    "windagent_session_id": f"agent:{self._new_id()}",
                    **node,
                }
                await repo.create_agent_run_bundle(
                    agent_instance_id=launch["agent_instance_id"],
                    agent_session_id=launch["agent_session_id"],
                    agent_run_id=launch["agent_run_id"],
                    task_node_run_id=launch["task_node_run_id"],
                    windagent_session_id=launch["windagent_session_id"],
                    conversation_id=conversation_id,
                    parent_task_id=parent_task_id,
                    plan_version_id=plan_version_id,
                    node_id=launch["node_id"],
                    agent_type=launch["agent_type"],
                    concurrency_group=launch["concurrency_group"],
                    dependency_node_ids=tuple(
                        edge["from_node_id"]
                        for edge in edges
                        if edge["to_node_id"] == launch["node_id"]
                    ),
                )
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=conversation_id,
                    event_type="agent_run_dispatching",
                    data={
                        "agent_run_id": launch["agent_run_id"],
                        "node_id": launch["node_id"],
                        "agent_type": launch["agent_type"],
                    },
                    agent_instance_id=launch["agent_instance_id"],
                    agent_session_id=launch["agent_session_id"],
                )
                launches.append(launch)
            if self._agent_loop_repo_factory is not None:
                try:
                    loop_repo = self._agent_loop_repo_factory(session)
                    for launch in launches:
                        await loop_repo.ensure_loop_state(agent_run_id=str(launch["agent_run_id"]), default_state="CREATED", limits={}, scope="conversation")
                except Exception:
                    pass
            await session.commit()

        # The durable scheduler, not WorkflowEngine's in-memory state, chooses
        # the initial runnable frontier.  Dependent nodes remain queued until
        # their pinned-plan parents terminally complete.
        #
        # Phase 7 control-plane mode: with no execution runtime composed, the
        # durable plan/ownership rows above are persisted but no subprocess is
        # dispatched.  Every returned agent stays ``queued`` for Worker pickup;
        # a run is never marked dispatched without a runtime handle.
        if self._has_runtime:
            dispatched = await self._dispatch_ready_nodes(parent_task_id)
            dispatched_by_run = {item.agent_run_id: item for item in dispatched}
        else:
            dispatched_by_run = {}
        result_launches = [
            dispatched_by_run.get(
                str(launch["agent_run_id"]),
                AgentLaunch(
                    agent_instance_id=str(launch["agent_instance_id"]),
                    agent_session_id=str(launch["agent_session_id"]),
                    agent_run_id=str(launch["agent_run_id"]),
                    node_id=str(launch["node_id"]),
                    agent_type=str(launch["agent_type"]),
                    runtime_run_id=None,
                    status="queued",
                ),
            )
            for launch in launches
        ]

        return OrchestrationResult(
            conversation_id=conversation_id,
            orchestrator_instance_id=orchestrator_instance_id,
            orchestrator_session_id=orchestrator_session_id,
            parent_task_id=parent_task_id,
            plan_version_id=plan_version_id,
            agents=tuple(result_launches),
        )

    async def revise_plan(
        self,
        *,
        conversation_id: str,
        parent_task_id: str,
        base_plan_version_id: str,
        subtasks: Sequence[Subtask],
    ) -> PlanRevisionResult:
        """Append a new immutable DAG snapshot without retargeting live runs.

        Existing AgentRun and TaskNodeRun records remain pinned to their
        original plan version.  The active-plan pointer moves only after the
        caller's base version wins a durable compare-and-swap.
        """
        if not base_plan_version_id.strip():
            raise ValueError("base_plan_version_id must not be empty")
        if not subtasks:
            raise ValueError("a plan revision requires at least one subtask")

        plan_version_id = self._new_id()
        async with self._session_factory() as session:
            repo = self._repo(session)
            context = await repo.revision_context(
                conversation_id=conversation_id,
                parent_task_id=parent_task_id,
            )
            if context is None:
                raise LookupError("running parent task not found in conversation")
            active_plan_version_id = str(context.get("active_plan_version_id") or "")
            if active_plan_version_id != base_plan_version_id:
                raise PlanRevisionConflict("active plan version changed; reload before revising")

            normalized = self._normalize_subtasks(str(context["objective"]), subtasks)
            if not normalized:
                raise ValueError("a plan revision requires at least one non-empty subtask")
            prepared, edges = self._prepare_plan(normalized, plan_version_id)
            dag = {
                "nodes": [
                    {
                        "node_id": node["node_id"],
                        "objective": node["objective"],
                        "agent_type": node["agent_type"],
                        "concurrency_group": node["concurrency_group"],
                    }
                    for node in prepared
                ],
                "edges": edges,
            }
            version = int(context["version"]) + 1
            switched = await repo.create_plan_revision(
                plan_version_id=plan_version_id,
                parent_task_id=parent_task_id,
                conversation_id=conversation_id,
                base_plan_version_id=base_plan_version_id,
                version=version,
                dag=dag,
            )
            if not switched:
                await session.rollback()
                raise PlanRevisionConflict("active plan version changed; reload before revising")
            await repo.create_nodes_and_edges(plan_version_id, prepared, edges)
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="task_plan_revised",
                data={
                    "parent_task_id": parent_task_id,
                    "base_plan_version_id": base_plan_version_id,
                    "plan_version_id": plan_version_id,
                    "version": version,
                },
            )
            await session.commit()

        return PlanRevisionResult(
            conversation_id=conversation_id,
            parent_task_id=parent_task_id,
            base_plan_version_id=base_plan_version_id,
            plan_version_id=plan_version_id,
            version=version,
        )

    async def stop_agent(self, agent_instance_id: str, *, conversation_id: str | None = None) -> bool:
        """Cancel only the selected agent's live runs; never its siblings."""
        async with self._session_factory() as session:
            repo = self._repo(session)
            runs = await repo.active_runs_for_agent(agent_instance_id, conversation_id)
            if not runs:
                return False

        if not self._has_runtime:
            # Control-plane mode: these active runs (queued/dispatching/running)
            # belong to the Worker's execution runtime, which is not composed
            # here.  Fail closed before any runtime/worktree/durable mutation so
            # this API never claims it cancelled execution it never owned.
            raise RuntimeError(
                f"execution runtime is not composed; cannot stop agent instance "
                f"'{agent_instance_id}' with active runs"
            )

        for run in runs:
            live = self._live_runs.get(str(run["agent_run_id"]))
            handle = live.handle if live else await self._reattach_handle(run)
            if handle is not None:
                await self._execution_registry.cancel(handle)

        # Runtime cancellation happens before removal.  A dirty linked checkout
        # is converted into a quarantined patch/untracked-file bundle first.
        await self._cleanup_agent_worktree(agent_instance_id, conversation_id)

        async with self._session_factory() as session:
            repo = self._repo(session)
            cancelled = await repo.mark_agent_cancelled(agent_instance_id, conversation_id)
            for run in cancelled:
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=await self._conversation_id_for_run(session, run),
                    event_type="agent_run_cancelled",
                    data={"agent_run_id": run["agent_run_id"]},
                    agent_instance_id=agent_instance_id,
                    agent_session_id=str(run["agent_session_id"]),
                )
            await session.commit()

        async with self._registry_lock:
            for run in runs:
                self._live_runs.pop(str(run["agent_run_id"]), None)
        return True

    async def reattach_live_runs(
        self,
        *,
        reconcile_worktrees: bool = True,
        resume_scheduler: bool = True,
    ) -> ReattachReport:
        """Rebuild the supervisor registry from durable AgentRun locators.

        Missing ownership is an orphan and is cancelled if the runtime can be
        reattached.  A live owned run whose adapter cannot reattach is retained
        in storage for the later recovery policy; it is never silently claimed.
        """
        worktree_report = (
            await self.reconcile_worktrees() if reconcile_worktrees else WorktreeReconcileReport()
        )
        runtime_orphans = set(worktree_report.runtime_orphaned_agent_instance_ids)
        async with self._session_factory() as session:
            rows = await self._repo(session).live_runs_with_owners()

        reattached: list[str] = []
        orphaned: list[str] = []
        unavailable: list[str] = []
        for row in rows:
            handle = await self._reattach_handle(row)
            has_owner = bool(row.get("owner_agent_instance_id") and row.get("owner_agent_session_id"))
            missing_worktree = str(row["agent_instance_id"]) in runtime_orphans
            if not has_owner or missing_worktree:
                if handle is not None:
                    await self._execution_registry.cancel(handle)
                orphaned.append(str(row["agent_run_id"]))
                continue
            if handle is None:
                unavailable.append(str(row["agent_run_id"]))
                continue
            async with self._registry_lock:
                self._live_runs[str(row["agent_run_id"])] = _LiveRun(
                    agent_instance_id=str(row["agent_instance_id"]),
                    agent_session_id=str(row["agent_session_id"]),
                    agent_run_id=str(row["agent_run_id"]),
                    handle=handle,
                )
            reattached.append(str(row["agent_run_id"]))

        if orphaned or reattached:
            async with self._session_factory() as session:
                repo = self._repo(session)
                for run_id in reattached:
                    await repo.mark_reattached(run_id)
                for run_id in orphaned:
                    await repo.mark_orphaned(run_id)
                await session.commit()
        # Recovery replays persisted scheduler state rather than restoring an
        # in-memory graph: terminal handles advance their DAG, then due queued
        # nodes are claimed under the same CAS/group-lock rules as new work.
        if resume_scheduler:
            await self.reconcile_runtime_completions()
            await self.schedule_due_nodes()
        return ReattachReport(
            tuple(reattached),
            tuple(orphaned),
            tuple(unavailable),
            worktree_report.reattached_worktree_ids,
            worktree_report.cleaned_worktree_ids,
        )

    async def reconcile_route_locks(self) -> tuple[str, ...]:
        """Rehydrate/reuse route locks for each persisted live AgentSession."""
        if self._route_lock_service is None:
            return ()
        async with self._session_factory() as session:
            rows = await self._repo(session).live_runs_with_owners()
        lock_ids: list[str] = []
        for row in rows:
            if not row.get("owner_agent_session_id"):
                continue
            lock, _ = self._resolve_route_lock(
                {
                    "agent_session_id": str(row["owner_agent_session_id"]),
                    "agent_type": str(row.get("owner_agent_type") or "generalist"),
                }
            )
            lock_ids.append(str(lock.lock_id))
        return tuple(lock_ids)

    async def reconcile_worktrees(self) -> WorktreeReconcileReport:
        """Reconcile DB ownership, Git worktree porcelain, and live runtimes.

        Rows with a surviving runtime are retained only when their linked
        checkout still exists.  Terminal/missing rows are cleaned according to
        the quarantine policy, and unowned managed worktrees are removed.
        """
        if self._worktree_manager is None:
            if self._release_telemetry is not None:
                self._release_telemetry.set_orphan_worktree_count(0)
            return WorktreeReconcileReport()

        async with self._session_factory() as session:
            rows = await self._repo(session).worktrees_for_reconciliation()

        attached: list[str] = []
        cleaned: list[str] = []
        runtime_orphans: list[str] = []
        known_paths = [str(row["path"]) for row in rows]
        for row in rows:
            allocation = self._allocation_from_worktree_row(row)
            exists = await asyncio.to_thread(self._worktree_manager.is_registered, allocation.path)
            if bool(row["runtime_active"]) and exists:
                attached.append(allocation.worktree_id)
                continue

            cleanup = await asyncio.to_thread(
                self._worktree_manager.cleanup_worktree,
                allocation,
            )
            status = cleanup.status if exists else "orphaned"
            error = cleanup.cleanup_error
            if not exists and error is None:
                error = "worktree missing from git worktree list during startup reconciliation"
            async with self._session_factory() as session:
                repo = self._repo(session)
                await repo.record_worktree_cleanup(
                    worktree_id=allocation.worktree_id,
                    status=status,
                    quarantine_path=str(cleanup.quarantine_path) if cleanup.quarantine_path else None,
                    cleanup_error=error,
                )
                await session.commit()
            cleaned.append(allocation.worktree_id)
            if bool(row["runtime_active"]):
                runtime_orphans.append(allocation.agent_instance_id)

        # An interrupted process can create the linked checkout just before its
        # DB transaction commits.  Git is authoritative for finding that orphan.
        await asyncio.to_thread(self._worktree_manager.cleanup_orphans, known_paths)
        report = WorktreeReconcileReport(
            tuple(attached), tuple(cleaned), tuple(runtime_orphans)
        )
        if self._release_telemetry is not None:
            self._release_telemetry.set_orphan_worktree_count(
                len(report.runtime_orphaned_agent_instance_ids)
            )
        return report

    @property
    def live_agent_run_ids(self) -> frozenset[str]:
        return frozenset(self._live_runs)

    async def list_agents(self, conversation_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            return await self._repo(session).list_agents(conversation_id)

    async def list_task_graphs(self, conversation_id: str) -> list[dict[str, Any]]:
        """Expose persisted active plan snapshots for the read-only workspace."""
        async with self._session_factory() as session:
            return await self._repo(session).list_task_graphs(conversation_id)

    async def list_plan_versions(
        self,
        *,
        conversation_id: str,
        parent_task_id: str,
    ) -> list[dict[str, Any]]:
        """Expose the full immutable snapshot history for a parent task."""
        async with self._session_factory() as session:
            return await self._repo(session).list_plan_versions(
                conversation_id=conversation_id,
                parent_task_id=parent_task_id,
            )

    # ─────────────────────────────────────────────────────────────────────
    # Control-plane seam (P4-R4B): V3 conversation/agent compatibility
    # surface.  These methods own sessions/transactions and expose the
    # dedicated multi-agent authority; routers never create repositories or
    # sessions.
    # ─────────────────────────────────────────────────────────────────────

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        title: str | None,
        objective: str,
        plan_version_id: str | None = None,
        orchestrator_instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist the canonical conversation, its orchestrator instance/session,
        and the start event atomically; return a ``ConversationResource``
        projection.
        """
        objective = objective.strip()
        if not objective:
            raise ValueError("objective must not be empty")
        orch_inst_id = orchestrator_instance_id or self._new_id()
        orch_session_id = self._new_id()
        async with self._session_factory() as session:
            repo = self._repo(session)
            projection = await repo.create_conversation(
                conversation_id=conversation_id,
                title=title,
                objective=objective,
                plan_version_id=plan_version_id,
                orchestrator_instance_id=orch_inst_id,
            )
            orch_inst_id, orch_session_id, created = (
                await repo.get_or_create_orchestrator(
                    conversation_id, orch_inst_id, orch_session_id
                )
            )
            if created:
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=conversation_id,
                    event_type="conversation.started",
                    data={"objective": objective},
                    agent_instance_id=orch_inst_id,
                    agent_session_id=orch_session_id,
                )
            await session.commit()
        return self._project_conversation(projection)

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            projection = await self._repo(session).get_conversation(conversation_id)
        return self._project_conversation(projection) if projection else None

    async def list_conversations(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            projections = await self._repo(session).list_conversations()
        return [self._project_conversation(projection) for projection in projections]

    async def launch_agent(
        self,
        *,
        agent_instance_id: str,
        conversation_id: str,
        definition_id: str,
        agent_type: str = "generalist",
        canonical_model_id: str | None = None,
        runtime_metadata: Mapping[str, Any] | None = None,
        status: str = "running",
    ) -> dict[str, Any]:
        """Persist a control-plane agent instance plus its session atomically."""
        agent_session_id = self._new_id()
        async with self._session_factory() as session:
            repo = self._repo(session)
            # Transaction-local invariant: the conversation must exist in the
            # same session/transaction that persists the agent instance and
            # event. This closes the router's check-then-use gap and prevents a
            # raw foreign-key/integrity failure for a direct orchestration
            # caller. Raising here rolls back the open transaction, so neither
            # the agent instance/session nor the conversation event is written.
            if await repo.get_conversation(conversation_id) is None:
                raise NotFoundError(f"Conversation '{conversation_id}' not found")
            projection = await repo.create_agent_instance(
                agent_instance_id=agent_instance_id,
                conversation_id=conversation_id,
                agent_session_id=agent_session_id,
                agent_type=agent_type,
                definition_id=definition_id,
                canonical_model_id=canonical_model_id,
                runtime_metadata=runtime_metadata,
                status=status,
                started_at=utc_now().isoformat() if status == "running" else None,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_instance_launched",
                data={
                    "agent_instance_id": agent_instance_id,
                    "definition_id": definition_id,
                },
                agent_instance_id=agent_instance_id,
                agent_session_id=agent_session_id,
            )
            await session.commit()
        return self._project_agent(projection)

    async def get_agent_instance(self, agent_instance_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            projection = await self._repo(session).get_agent_instance(agent_instance_id)
        return self._project_agent(projection) if projection else None

    async def list_agent_instances(
        self, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            projections = await self._repo(session).list_agent_instances(conversation_id)
        return [self._project_agent(projection) for projection in projections]

    async def start_agent(self, agent_instance_id: str) -> dict[str, Any] | None:
        """Control-plane start; fails closed while a real run is still live.

        An instance that ever had a real ``agent_runs`` row (live or terminal)
        cannot be control-started: doing so would mark it RUNNING without
        resurrecting that runtime. Control-only instances with no run history
        keep the existing start compatibility behavior.
        """
        async with self._session_factory() as session:
            repo = self._repo(session)
            runs = await repo.active_runs_for_agent(agent_instance_id)
            if runs:
                raise RuntimeError(
                    f"agent instance '{agent_instance_id}' has live runs; cannot control-start"
                )
            if await repo.has_agent_run_history(agent_instance_id):
                raise RuntimeError(
                    f"agent instance '{agent_instance_id}' has real run history; "
                    "cannot control-start without resurrecting a runtime"
                )
        now_iso = utc_now().isoformat()
        async with self._session_factory() as session:
            repo = self._repo(session)
            projection = await repo.transition_agent_lifecycle(
                agent_instance_id=agent_instance_id,
                target_status="running",
                profile_updates={
                    "started_at": now_iso,
                    "stopped_at": None,
                    "current_tool": None,
                },
            )
            if projection is None:
                await session.rollback()
                return None
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=projection["conversation_id"],
                event_type="agent_instance_started",
                data={"agent_instance_id": agent_instance_id},
                agent_instance_id=agent_instance_id,
            )
            await session.commit()
        return self._project_agent(projection)

    async def stop_agent_instance(
        self, agent_instance_id: str, conversation_id: str | None = None
    ) -> dict[str, Any] | None:
        """Stop an agent instance.

        Real runtime cancellation is preserved through ``stop_agent`` when live
        runs exist; instances with no active run get a control lifecycle update.
        """
        async with self._session_factory() as session:
            repo = self._repo(session)
            runs = await repo.active_runs_for_agent(agent_instance_id, conversation_id)
        if runs:
            await self.stop_agent(agent_instance_id, conversation_id=conversation_id)
        else:
            now_iso = utc_now().isoformat()
            async with self._session_factory() as session:
                repo = self._repo(session)
                projection = await repo.transition_agent_lifecycle(
                    agent_instance_id=agent_instance_id,
                    target_status="cancelled",
                    profile_updates={"stopped_at": now_iso, "current_tool": None},
                )
                if projection is None:
                    await session.rollback()
                    return None
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=projection["conversation_id"],
                    event_type="agent_instance_stopped",
                    data={"agent_instance_id": agent_instance_id},
                    agent_instance_id=agent_instance_id,
                )
                await session.commit()
        return await self.get_agent_instance(agent_instance_id)

    async def restart_agent(self, agent_instance_id: str) -> dict[str, Any] | None:
        """Control-plane restart; fails closed while a real run is still live.

        A control restart never claims a runtime was resurrected for an agent
        with an existing real-run state that cannot safely be restarted. An
        instance that ever had a real ``agent_runs`` row (live or terminal)
        cannot be control-restarted; control-only instances with no run history
        keep the existing restart compatibility behavior.
        """
        async with self._session_factory() as session:
            repo = self._repo(session)
            runs = await repo.active_runs_for_agent(agent_instance_id)
            if runs:
                raise RuntimeError(
                    f"agent instance '{agent_instance_id}' has live runs; cannot restart"
                )
            if await repo.has_agent_run_history(agent_instance_id):
                raise RuntimeError(
                    f"agent instance '{agent_instance_id}' has real run history; "
                    "cannot control-restart without resurrecting a runtime"
                )
        now_iso = utc_now().isoformat()
        async with self._session_factory() as session:
            repo = self._repo(session)
            projection = await repo.transition_agent_lifecycle(
                agent_instance_id=agent_instance_id,
                target_status="running",
                profile_updates={
                    "started_at": now_iso,
                    "stopped_at": None,
                    "current_tool": None,
                },
            )
            if projection is None:
                await session.rollback()
                return None
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=projection["conversation_id"],
                event_type="agent_instance_restarted",
                data={"agent_instance_id": agent_instance_id},
                agent_instance_id=agent_instance_id,
            )
            await session.commit()
        return self._project_agent(projection)

    async def conversation_events(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return the authoritative ordered event replay for one conversation."""
        async with self._session_factory() as session:
            return await self._repo(session).conversation_events_after(conversation_id)

    async def append_demo_event(
        self,
        *,
        event_id: str,
        conversation_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Idempotently append a demo event through the dedicated event store."""
        async with self._session_factory() as session:
            await self._repo(session).append_event_if_absent(
                event_id=event_id,
                conversation_id=conversation_id,
                event_type=event_type,
                data=payload,
            )
            await session.commit()

    @staticmethod
    def _project_conversation(conv: Mapping[str, Any]) -> dict[str, Any]:
        projection = dict(conv)
        projection["status"] = _CANONICAL_TO_API_STATUS.get(
            str(projection.get("status", "")), projection.get("status", "ACTIVE")
        )
        return projection

    @staticmethod
    def _project_agent(inst: Mapping[str, Any]) -> dict[str, Any]:
        projection = dict(inst)
        projection["status"] = _CANONICAL_TO_API_STATUS.get(
            str(projection.get("status", "")), projection.get("status", "IDLE")
        )
        return projection

    @staticmethod
    def _canonical_status(api_status: str) -> str:
        return _API_TO_CANONICAL_STATUS.get(api_status.upper(), api_status.lower())

    async def complete_agent_node(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        succeeded: bool,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
        fencing_token: str | None = None,
    ) -> NodeCompletionResult:
        """CAS-finalize one running node, then advance the durable DAG.

        A cancelled node no longer satisfies the ``state='running'`` compare
        condition, so a late runtime completion is ignored and cancellation has
        explicit precedence.
        """
        async with self._session_factory() as session:
            repo = self._repo(session)
            run = await repo.running_agent_run(agent_instance_id, conversation_id, fencing_token)
            if run is None:
                return NodeCompletionResult(applied=False)
            outcome = await repo.finalize_running_node(
                agent_run_id=str(run["agent_run_id"]),
                task_node_run_id=str(run["task_node_run_id"]),
                parent_task_id=str(run["parent_task_id"]),
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]),
                expected_node_version=int(run["node_version"]),
                succeeded=succeeded,
                result=redact_before_persist(dict(result or {})),
                error=error,
            )
            if outcome is None:
                await session.rollback()
                return NodeCompletionResult(applied=False)
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_node_completed" if succeeded else "agent_node_retry_or_failed",
                data={
                    "agent_run_id": str(run["agent_run_id"]),
                    "task_node_run_id": str(run["task_node_run_id"]),
                    "state": outcome["state"],
                },
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]),
            )
            await session.commit()
        if not succeeded:
            try:
                _bc = self._budget_controller()
                if _bc is not None:
                    await _bc.record_retry(str(run["agent_run_id"]))
            except Exception:
                pass
        async with self._registry_lock:
            self._live_runs.pop(str(run["agent_run_id"]), None)
        dispatched = await self._dispatch_ready_nodes(str(run["parent_task_id"]))
        next_retry_at = outcome["next_retry_at"]
        return NodeCompletionResult(
            applied=True,
            state=str(outcome["state"]),
            next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
            dispatched_agent_run_ids=tuple(item.agent_run_id for item in dispatched),
        )

    async def schedule_due_nodes(self, parent_task_id: str | None = None) -> tuple[AgentLaunch, ...]:
        """Run one production scheduler tick; safe to call after recovery."""
        if not self._has_runtime:
            # Control-plane mode: no runtime exists, so nothing can be claimed
            # or dispatched.  Durable rows remain queued for Worker pickup.
            return ()
        if parent_task_id is None:
            claims = await self._plan_scheduler.claim_ready_nodes()
            return tuple(await self._dispatch_claimed_nodes(claims))
        return tuple(await self._dispatch_ready_nodes(parent_task_id))

    async def reconcile_runtime_completions(self) -> tuple[str, ...]:
        """Advance durable plans from terminal runtime handles after restart/ticks."""
        if not self._has_runtime:
            return ()
        completed: list[str] = []
        for live in tuple(self._live_runs.values()):
            status = await self._execution_registry.get_status(live.handle)
            if status.status not in (RuntimeStatusEnum.COMPLETED, RuntimeStatusEnum.FAILED):
                continue
            result = await self._execution_registry.get_result(live.handle)
            outcome = await self.complete_agent_node(
                conversation_id=await self._conversation_id_for_agent(live.agent_instance_id),
                agent_instance_id=live.agent_instance_id,
                succeeded=status.status == RuntimeStatusEnum.COMPLETED,
                result=result.result_data or {},
                error=result.error,
                fencing_token=live.handle.fencing_token,
            )
            if outcome.applied:
                completed.append(live.agent_run_id)
        return tuple(completed)

    async def execute_idempotent_tool(
        self,
        *,
        agent_instance_id: str | None,
        tool_name: str,
        idempotency_key: str,
        arguments: Mapping[str, Any],
        operation: Callable[[], Awaitable[tuple[Any, str | None]]],
    ) -> ToolExecutionResult:
        """Reserve a unique ToolExecution before an agent causes side effects."""
        claimant = agent_instance_id or "orchestrator"
        async with self._session_factory() as session:
            reservation = await self._repo(session).reserve_tool_execution(
                tool_execution_id=self._new_id(),
                idempotency_key=idempotency_key,
                agent_instance_id=agent_instance_id,
                tool_name=tool_name,
                arguments_redacted=redact_before_persist(dict(arguments)),
                claimant=claimant,
            )
            await session.commit()
        if not reservation["claimed"]:
            if self._release_telemetry is not None:
                self._release_telemetry.record_duplicate_tool_execution()
            return ToolExecutionResult(
                tool_execution_id=str(reservation["tool_execution_id"]),
                executed=False,
                status=str(reservation["status"]),
                result_ref=reservation.get("result_ref"),
            )

        _, result_ref = await operation()
        async with self._session_factory() as session:
            completed = await self._repo(session).complete_tool_execution(
                tool_execution_id=str(reservation["tool_execution_id"]),
                claimant=claimant,
                result_ref=result_ref,
            )
            await session.commit()
        return ToolExecutionResult(
            tool_execution_id=str(reservation["tool_execution_id"]),
            executed=True,
            status="completed" if completed else "running",
            result_ref=result_ref,
        )

    async def stream_agent_output(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        stream_id: str,
        chunks: AsyncIterable[str],
    ) -> AsyncIterator[str]:
        """Yield live stream chunks and audit partial bytes on an exception.

        The method intentionally never emits an assistant transcript event for
        streamed bytes.  A failed stream is represented only by an audit-only
        ``partial_stream_artifacts`` row plus a metadata event.
        """
        captured: list[str] = []
        sequence = 0
        try:
            async for chunk in chunks:
                text_chunk = str(chunk)
                captured.append(text_chunk)
                sequence += 1
                yield text_chunk
        except Exception as exc:
            await self.audit_partial_stream(
                conversation_id=conversation_id,
                agent_instance_id=agent_instance_id,
                stream_id=stream_id,
                sequence=sequence,
                content="".join(captured),
                failure_reason=str(exc),
            )
            raise

    async def audit_partial_stream(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str | None,
        stream_id: str,
        sequence: int,
        content: str,
        failure_reason: str,
    ) -> str:
        """Persist a redacted partial artifact without polluting transcripts."""
        partial_artifact_id = self._new_id()
        async with self._session_factory() as session:
            repo = self._repo(session)
            run = (
                await repo.routable_agent_run(agent_instance_id, conversation_id)
                if agent_instance_id is not None
                else None
            )
            redacted_content = str(
                redact_before_persist({"content": content}).get("content", "")
            )
            redacted_reason = str(
                redact_before_persist({"reason": failure_reason}).get("reason", "stream interrupted")
            )
            await repo.record_partial_stream_artifact(
                partial_artifact_id=partial_artifact_id,
                conversation_id=conversation_id,
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]) if run else None,
                agent_run_id=str(run["agent_run_id"]) if run else None,
                stream_id=stream_id,
                sequence=sequence,
                content_redacted=redacted_content,
                failure_reason=redacted_reason,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_stream_partial_audited",
                data={
                    "partial_artifact_id": partial_artifact_id,
                    "stream_id": stream_id,
                    "sequence": sequence,
                    "audit_only": True,
                },
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]) if run else None,
            )
            await session.commit()
        return partial_artifact_id

    async def execute_provider_turn(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        prompt: str,
        messages: Sequence[Mapping[str, Any]] = (),
        max_output_tokens: int | None = None,
    ) -> AgentTurnResult:
        """Execute one agent turn via the locked canonical provider route.

        The lock is resolved (or reused) on the AgentSession immediately before
        execution.  The resulting turn snapshot and coordinator attempts are
        durable; no prompt, completion, credential, or provider headers are
        stored in the routing audit trail.
        """
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")

        async with self._session_factory() as session:
            repo = self._repo(session)
            run = await repo.routable_agent_run(agent_instance_id, conversation_id)
            if run is None:
                raise LookupError("running agent not found")
            try:
                _bc = self._budget_controller()
                if _bc is not None:
                    await _bc.authorize_turn(str(run["agent_run_id"]))
            except Exception as exc:
                from windagent_orchestration.agent_loop.budget_controller import BudgetExhaustedError
                if isinstance(exc, BudgetExhaustedError):
                    raise RuntimeError(f"budget exhausted: {exc.reason}") from exc
                if "no such table" not in str(exc).lower():
                    raise
            route_lock, routing_snapshot = self._resolve_route_lock(run)
            turn_id = self._new_id()
            await repo.create_agent_turn(
                turn_id=turn_id,
                agent_run_id=str(run["agent_run_id"]),
                agent_session_id=str(run["agent_session_id"]),
                route_lock_id=str(route_lock.lock_id),
                canonical_model_id=str(route_lock.canonical_model_id),
                routing_snapshot=routing_snapshot,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_turn_started",
                data={
                    "turn_id": turn_id,
                    "agent_run_id": str(run["agent_run_id"]),
                    "routing_snapshot": routing_snapshot,
                },
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]),
            )
            await session.commit()

        request_messages = [dict(message) for message in messages]
        if not request_messages:
            request_messages = [{"role": "user", "content": prompt}]
        request = ProviderRequest(
            model_id=str(route_lock.canonical_model_id),
            prompt=prompt,
            messages=request_messages,
            request_id=turn_id,
            max_output_tokens=max_output_tokens,
        )

        try:
            if self._provider_execution_coordinator is None:
                raise RuntimeError("provider execution coordinator is not configured")
            response = await self._provider_execution_coordinator.execute(
                request,
                route_lock,
                turn_id=turn_id,
            )
        except Exception as exc:
            await self._record_turn_failure(
                conversation_id=conversation_id,
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]),
                agent_run_id=str(run["agent_run_id"]),
                turn_id=turn_id,
                routing_snapshot=routing_snapshot,
                error_class=exc.__class__.__name__,
            )
            try:
                _bc = self._budget_controller()
                if _bc is not None:
                    await _bc.record_model_failure(str(run["agent_run_id"]))
            except Exception:
                pass
            raise

        binding = {
            "provider_binding_id": response.raw_metadata.get("provider_binding_id"),
            "endpoint_id": response.endpoint_id,
            "provider_model_id": response.provider_model_id,
        }
        final_snapshot = {**routing_snapshot, "binding": binding}
        summary = {
            **binding,
            "finish_reason": response.finish_reason,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.complete_agent_turn(
                turn_id=turn_id,
                agent_run_id=str(run["agent_run_id"]),
                routing_snapshot=final_snapshot,
                response_summary=summary,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_turn_completed",
                data={"turn_id": turn_id, "agent_run_id": str(run["agent_run_id"]), "routing_snapshot": final_snapshot},
                agent_instance_id=agent_instance_id,
                agent_session_id=str(run["agent_session_id"]),
            )
            await session.commit()
        try:
            _bc = self._budget_controller()
            if _bc is not None:
                tokens = int(summary.get("prompt_tokens") or 0) + int(summary.get("completion_tokens") or 0)
                await _bc.record_turn_tokens(str(run["agent_run_id"]), tokens=tokens, cost=0.0)
        except Exception:
            pass
        return AgentTurnResult(
            turn_id=turn_id,
            agent_instance_id=agent_instance_id,
            agent_session_id=str(run["agent_session_id"]),
            agent_run_id=str(run["agent_run_id"]),
            canonical_model_id=str(response.canonical_model_id or route_lock.canonical_model_id),
            route_lock_id=str(route_lock.lock_id),
            routing_snapshot=final_snapshot,
            text=response.text if response.text is not None else response.content,
            finish_reason=response.finish_reason,
        )

    async def list_routing_turns(self, conversation_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            return await self._repo(session).list_routing_turns(conversation_id)

    async def routing_turn_detail(
        self, conversation_id: str, turn_id: str
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            return await self._repo(session).routing_turn_detail(conversation_id, turn_id)

    async def _dispatch_agent_run(
        self,
        *,
        conversation_id: str,
        parent_task_id: str,
        plan_version_id: str,
        launch: Mapping[str, Any],
    ) -> AgentLaunch:
        if not self._has_runtime:
            # Fail closed before any mutation: no runtime handle exists, so a
            # run must never be marked dispatched.  The durable submission
            # contract (queued rows) is preserved for Worker pickup.
            raise RuntimeError(
                "execution runtime is not composed; cannot dispatch agent runs"
            )
        worktree: Any | None = None
        try:
            routing_snapshot = self._acquire_route_lock(launch)
            if str(launch["agent_type"]) == "coding":
                worktree = await self._ensure_coding_worktree(
                    conversation_id=conversation_id,
                    launch=launch,
                )
            parameters = {"objective": str(launch["objective"])}
            context = {
                "conversation_id": conversation_id,
                "parent_task_id": parent_task_id,
                "plan_version_id": plan_version_id,
                "routing_snapshot": routing_snapshot,
            }
            if worktree is not None:
                # The runtime only receives this service-derived linked checkout;
                # frontend request data never participates in this decision.
                parameters["workspace_root"] = str(worktree.path)
                context["workspace_root"] = str(worktree.path)
                context["worktree_id"] = worktree.worktree_id
            handle = await self._execution_registry.dispatch(
                ExecutionRequest(
                    step_run_id=str(launch["task_node_run_id"]),
                    workflow_run_id=str(launch["windagent_session_id"]),
                    tool_name=f"agent_{launch['agent_type']}",
                    parameters=parameters,
                    attempt_id=str(launch["agent_run_id"]),
                    fencing_token=str(launch["fencing_token"]),
                    context=context,
                )
            )
        except Exception as exc:
            async with self._session_factory() as session:
                repo = self._repo(session)
                await repo.record_dispatch_failure(str(launch["agent_run_id"]), str(exc))
                await repo.release_concurrency_lock(str(launch["task_node_run_id"]))
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=conversation_id,
                    event_type="agent_run_failed_to_dispatch",
                    data={"agent_run_id": launch["agent_run_id"], "reason": str(exc)},
                    agent_instance_id=str(launch["agent_instance_id"]),
                    agent_session_id=str(launch["agent_session_id"]),
                )
                await session.commit()
            if worktree is not None:
                await self._cleanup_agent_worktree(
                    str(launch["agent_instance_id"]), conversation_id
                )
            return AgentLaunch(
                agent_instance_id=str(launch["agent_instance_id"]),
                agent_session_id=str(launch["agent_session_id"]),
                agent_run_id=str(launch["agent_run_id"]),
                node_id=str(launch["node_id"]),
                agent_type=str(launch["agent_type"]),
                runtime_run_id=None,
                status="failed",
            )

        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.record_dispatch(
                agent_run_id=str(launch["agent_run_id"]),
                agent_instance_id=str(launch["agent_instance_id"]),
                agent_session_id=str(launch["agent_session_id"]),
                runtime_handle_id=handle.handle_id,
                runtime_run_id=handle.runtime_run_id,
                fencing_token=str(launch["fencing_token"]),
                routing_snapshot=routing_snapshot,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_run_started",
                data={
                    "agent_run_id": launch["agent_run_id"],
                    "runtime_run_id": handle.runtime_run_id,
                    "routing_snapshot": routing_snapshot,
                },
                agent_instance_id=str(launch["agent_instance_id"]),
                agent_session_id=str(launch["agent_session_id"]),
            )
            await session.commit()
        async with self._registry_lock:
            self._live_runs[str(launch["agent_run_id"])] = _LiveRun(
                agent_instance_id=str(launch["agent_instance_id"]),
                agent_session_id=str(launch["agent_session_id"]),
                agent_run_id=str(launch["agent_run_id"]),
                handle=handle,
            )
        # Local/fake runtimes may complete synchronously.  Reconcile their
        # durable state here; long-running runtimes are reconciled by worker
        # ticks via ``reconcile_runtime_completions``.
        await self._reconcile_handle_if_terminal(
            conversation_id=conversation_id,
            agent_instance_id=str(launch["agent_instance_id"]),
            handle=handle,
        )
        return AgentLaunch(
            agent_instance_id=str(launch["agent_instance_id"]),
            agent_session_id=str(launch["agent_session_id"]),
            agent_run_id=str(launch["agent_run_id"]),
            node_id=str(launch["node_id"]),
            agent_type=str(launch["agent_type"]),
            runtime_run_id=handle.runtime_run_id,
            status="running",
        )

    async def _dispatch_ready_nodes(self, parent_task_id: str) -> list[AgentLaunch]:
        if not self._has_runtime:
            # Control-plane mode: never claim nodes for a runtime that does not
            # exist.  The durable rows stay queued for Worker pickup.
            return []
        claims = await self._plan_scheduler.claim_ready_nodes(parent_task_id)
        return await self._dispatch_claimed_nodes(claims)

    async def _dispatch_claimed_nodes(
        self, claims: Sequence[Mapping[str, Any]]
    ) -> list[AgentLaunch]:
        if not self._has_runtime:
            return []
        dispatched: list[AgentLaunch] = []
        for claim in claims:
            dispatched.append(
                await self._dispatch_agent_run(
                    conversation_id=str(claim["conversation_id"]),
                    parent_task_id=str(claim["parent_task_id"]),
                    plan_version_id=str(claim["plan_version_id"]),
                    launch=claim,
                )
            )
        return dispatched

    async def _reconcile_handle_if_terminal(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        handle: ExecutionHandle,
    ) -> None:
        if not self._has_runtime:
            return
        status = await self._execution_registry.get_status(handle)
        if status.status not in (RuntimeStatusEnum.COMPLETED, RuntimeStatusEnum.FAILED):
            return
        result = await self._execution_registry.get_result(handle)
        await self.complete_agent_node(
            conversation_id=conversation_id,
            agent_instance_id=agent_instance_id,
            succeeded=status.status == RuntimeStatusEnum.COMPLETED,
            result=result.result_data or {},
            error=result.error,
            fencing_token=handle.fencing_token,
        )

    def _acquire_route_lock(self, launch: Mapping[str, Any]) -> dict[str, Any]:
        _, snapshot = self._resolve_route_lock(launch)
        return snapshot

    def _resolve_route_lock(self, agent: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
        if self._route_lock_service is None:
            raise RuntimeError("route lock service is not configured")
        # RouteLockService is injected at the composition boundary.  It only
        # requires this stable context shape, not a provider-owned class.
        context = SimpleNamespace(
            scope_id=str(agent["agent_session_id"]),
            scope_type="agent_session",
            agent_type=str(agent["agent_type"]),
            workflow_type="conversation",
            has_tools=True,
        )
        lock = self._route_lock_service.resolve_or_create_lock(context)
        snapshot = {
            "lock_id": lock.lock_id,
            "canonical_model_id": lock.canonical_model_id,
            "policy_version": lock.routing_snapshot.rule_version,
            "binding": None,
            "rule": {
                "rule_id": getattr(lock.routing_snapshot, "rule_id", None),
                "reason": getattr(lock.routing_snapshot, "reason", None),
            },
        }
        return lock, snapshot

    async def _record_turn_failure(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        agent_session_id: str,
        agent_run_id: str,
        turn_id: str,
        routing_snapshot: Mapping[str, Any],
        error_class: str,
    ) -> None:
        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.fail_agent_turn(
                turn_id=turn_id,
                agent_run_id=agent_run_id,
                routing_snapshot=routing_snapshot,
                error_class=error_class,
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="agent_turn_failed",
                data={"turn_id": turn_id, "agent_run_id": agent_run_id, "error_class": error_class},
                agent_instance_id=agent_instance_id,
                agent_session_id=agent_session_id,
            )
            await session.commit()

    async def _reattach_handle(self, run: Mapping[str, Any]) -> ExecutionHandle | None:
        if not self._has_runtime:
            return None
        runtime_run_id = run.get("runtime_run_id")
        if not runtime_run_id:
            return None
        return await self._execution_registry.reattach(str(runtime_run_id))

    async def _ensure_coding_worktree(
        self,
        *,
        conversation_id: str,
        launch: Mapping[str, Any],
    ) -> Any | None:
        if self._worktree_manager is None:
            # Direct service construction remains useful for control-plane unit
            # tests and non-production dry runs.  Production composition fails
            # closed before exposing this service when no repository is set.
            return None
        agent_instance_id = str(launch["agent_instance_id"])
        async with self._session_factory() as session:
            existing = await self._repo(session).active_worktree_for_agent(agent_instance_id)
        if existing is not None:
            allocation = self._allocation_from_worktree_row(existing)
            if await asyncio.to_thread(self._worktree_manager.is_registered, allocation.path):
                return allocation

        allocation = await asyncio.to_thread(
            self._worktree_manager.create_worktree,
            str(existing["worktree_id"]) if existing is not None else agent_instance_id,
            agent_instance_id=agent_instance_id,
            branch=str(existing["branch"]) if existing is not None else None,
        )
        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.upsert_worktree(
                worktree_id=allocation.worktree_id,
                agent_instance_id=allocation.agent_instance_id,
                agent_run_id=str(launch["agent_run_id"]),
                path=str(allocation.path),
                branch=allocation.branch,
                repo_root=str(allocation.repo_root),
            )
            await repo.append_event(
                event_id=self._new_id(),
                conversation_id=conversation_id,
                event_type="coding_worktree_provisioned",
                data={
                    "worktree_id": allocation.worktree_id,
                    "branch": allocation.branch,
                },
                agent_instance_id=agent_instance_id,
                agent_session_id=str(launch["agent_session_id"]),
            )
            await session.commit()
        return allocation

    async def _cleanup_agent_worktree(
        self, agent_instance_id: str, conversation_id: str | None
    ) -> None:
        if self._worktree_manager is None:
            return
        async with self._session_factory() as session:
            row = await self._repo(session).active_worktree_for_agent(agent_instance_id)
        if row is None:
            return
        allocation = self._allocation_from_worktree_row(row)
        cleanup = await asyncio.to_thread(self._worktree_manager.cleanup_worktree, allocation)
        async with self._session_factory() as session:
            repo = self._repo(session)
            await repo.record_worktree_cleanup(
                worktree_id=allocation.worktree_id,
                status=cleanup.status,
                quarantine_path=str(cleanup.quarantine_path) if cleanup.quarantine_path else None,
                cleanup_error=cleanup.cleanup_error,
            )
            if conversation_id is not None:
                await repo.append_event(
                    event_id=self._new_id(),
                    conversation_id=conversation_id,
                    event_type="coding_worktree_cleaned",
                    data={
                        "worktree_id": allocation.worktree_id,
                        "status": cleanup.status,
                        "quarantined": cleanup.quarantine_path is not None,
                    },
                    agent_instance_id=agent_instance_id,
                )
            await session.commit()

    @staticmethod
    def _allocation_from_worktree_row(row: Mapping[str, Any]) -> WorktreeReference:
        return WorktreeReference(
            worktree_id=str(row["worktree_id"]),
            agent_instance_id=str(row["agent_instance_id"]),
            path=Path(str(row["path"])).resolve(),
            branch=str(row["branch"]),
            repo_root=Path(str(row["repo_root"])).resolve(),
        )

    async def _conversation_id_for_run(self, session: Any, run: Mapping[str, Any]) -> str:
        return await self._repo(session).conversation_id_for_parent_task(
            str(run["parent_task_id"])
        )

    async def _conversation_id_for_agent(self, agent_instance_id: str) -> str:
        async with self._session_factory() as session:
            return await self._repo(session).conversation_id_for_agent(agent_instance_id)

    @staticmethod
    def _derive_agent_type(objective: str) -> str:
        text = objective.lower()
        if any(word in text for word in ("research", "nghiên cứu", "tìm hiểu", "search")):
            return "research"
        if any(word in text for word in ("browser", "web", "trình duyệt")):
            return "browser"
        if any(word in text for word in ("code", "implement", "fix", "sửa", "lập trình")):
            return "coding"
        return "generalist"

    @classmethod
    def _normalize_subtasks(
        cls, objective: str, subtasks: Sequence[Subtask]
    ) -> tuple[Subtask, ...]:
        if subtasks:
            return tuple(
                Subtask(
                    objective=item.objective.strip(),
                    node_id=item.node_id,
                    depends_on=tuple(item.depends_on),
                    concurrency_group=item.concurrency_group,
                )
                for item in subtasks
                if item.objective.strip()
            )
        # No role is supplied by the caller.  A two-track default makes the
        # Phase-2 control plane useful before the Phase-4 DAG scheduler owns
        # dependencies and retries.
        return (
            Subtask(objective=f"Research and clarify: {objective}", node_id="research"),
            Subtask(objective=f"Implement or execute: {objective}", node_id="execution"),
        )

    def _prepare_plan(
        self,
        subtasks: Sequence[Subtask],
        plan_version_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Derive a validated, version-scoped DAG from user-facing subtasks."""
        prepared: list[dict[str, Any]] = []
        node_id_map: dict[str, str] = {}
        for index, item in enumerate(subtasks):
            requested_id = item.node_id or f"node-{index + 1}"
            if requested_id in node_id_map:
                raise ValueError(f"duplicate subtask node_id: {requested_id}")
            # ``task_nodes.node_id`` is globally primary-keyed.  Prefixing it
            # with the immutable version lets names safely recur across edits.
            node_id = f"{plan_version_id}:{requested_id}"
            node_id_map[requested_id] = node_id
            prepared.append(
                {
                    "node_id": node_id,
                    "position": index,
                    "objective": item.objective,
                    "agent_type": self._derive_agent_type(item.objective),
                    "concurrency_group": item.concurrency_group,
                    "depends_on": item.depends_on,
                }
            )

        edges: list[dict[str, str]] = []
        for item in prepared:
            for source in item["depends_on"]:
                if source not in node_id_map:
                    raise ValueError(f"unknown dependency node_id: {source}")
                edges.append(
                    {
                        "edge_id": self._new_id(),
                        "from_node_id": node_id_map[source],
                        "to_node_id": item["node_id"],
                    }
                )
        self._assert_acyclic(prepared, edges)
        return prepared, edges

    @staticmethod
    def _assert_acyclic(nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, str]]) -> None:
        node_ids = {str(node["node_id"]) for node in nodes}
        outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
        for edge in edges:
            source, target = str(edge["from_node_id"]), str(edge["to_node_id"])
            if source not in node_ids or target not in node_ids:
                raise ValueError("plan edge references an unknown node")
            if target not in outgoing[source]:
                outgoing[source].add(target)
                indegree[target] += 1
        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            node_id = ready.pop()
            visited += 1
            for target in outgoing[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(node_ids):
            raise ValueError("task plan must be acyclic")

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())
