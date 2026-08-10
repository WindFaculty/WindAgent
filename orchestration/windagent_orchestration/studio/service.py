"""StudioRunService — sole new Story orchestration authority (Plan A — A4).

Implements ``StudioRunOrchestratorPort``. Public behavior contract:

- ``start_or_resume_run``: builds the deterministic DAG, persists run + node
  state, THEN submits runnable nodes durably and marks them DISPATCHED only
  with the committed queue task identity. A resumed run never re-submits a
  node that already holds a committed task identity.
- ``record_approval``: approval waits are durable run state (WAITING_APPROVAL);
  only an APPROVED decision resumes the DAG through this service.
- ``cancel_run``: idempotent; terminal history is never rewritten.
- ``StudioCompletionReconciler.handle_task_result``: the ONLY path that turns
  durable task final state into DAG advancement. Stale completions, duplicate
  deliveries, and out-of-order results are rejected or no-op'd.

Retries: a FAILED task result with attempts left parks the node back in
DISPATCHED with ``task_id=None`` and attempt+1; the post-commit submission
loop re-dispatches it with a fresh (run, node, attempt) idempotency key.
Crash windows are therefore resumable: submission committed before the node
update is found by idempotency, and a node committed as DISPATCHED without a
task identity is re-submitted on the next resume/reconcile.

Non-goals (B phases): idea selection content binding, screenplay review
semantics, revision workflows. Those commands run through the same durable
path once B handlers exist; the synchronous variants implemented here are the
A2 contract surface kept fail-closed (no fake fallback).
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

# Session factory is an opaque ``Any`` here on purpose: the orchestration layer
# must stay ORM-free (architecture checker forbids sqlalchemy imports).
AsyncSessionFactory = Any

from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateEpisodeResult,
    CreateSeriesCommand,
    CreateSeriesResult,
    DeriveRevisionCommand,
    DeriveRevisionResult,
    LockScreenplayCommand,
    LockScreenplayResult,
    RecordApprovalCommand,
    RecordApprovalResult,
    SelectIdeaCommand,
    SelectIdeaResult,
    StartRunCommand,
    StartRunResult,
)
from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioNotFoundError,
    StudioStaleNodeError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.contracts.studio.models import (
    StudioArtifactRef,
    StudioNodeStatus,
    StudioTaskEnvelope,
    StudioTaskResult,
    StudioTaskStatus,
    StudioTaskType,
)
from windagent_core.contracts.studio.ports import (
    StudioRunOrchestratorPort,
    StudioTaskSubmissionPort,
)
from windagent_core.domain.studio.approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyService,
)
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.lifecycle import (
    ApprovalCheckpoint,
    CHECKPOINT_TO_REVIEW_STATE,
    EpisodeState,
    EpisodeStateMachine,
)
from windagent_core.domain.studio.revision import (
    StudioInvalidationIntent,
    StudioLockState,
    StudioRevisionService,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.events.studio import StudioEventCatalog, StudioEventEnvelope
from windagent_orchestration.studio.dag import (
    NODE_LOCK,
    build_story_dag,
    dependencies_terminal,
    initial_node_states,
)
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

DEFAULT_APPROVAL_POLICY_ID = "studio.default"
DEFAULT_RETRY_BUDGET = 3
RUN_TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _id_from_key(prefix: str, idempotency_key: str) -> str:
    """Deterministic aggregate id from an idempotency key (repeat == same id)."""
    return f"{prefix}_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]}"


async def submit_runnable_nodes(
    session_factory: AsyncSessionFactory,
    submission: StudioTaskSubmissionPort,
    run_id: StudioRunId,
    *,
    retry_budget: int,
    policy_id: str,
) -> None:
    """Durable dispatch of RUNNABLE (and task-less DISPATCHED) nodes.

    Queue submission commits FIRST (durable task identity), the node transition
    to DISPATCHED + TASK_SUBMITTED event SECOND, atomically in the Studio UoW.
    A crash between the two leaves the node RUNNABLE/DISPATCHED-without-task;
    the next resume/reconcile re-submits and the outbox dedup key returns the
    original committed task identity.
    """
    service = StudioRunService(
        session_factory, submission, retry_budget=retry_budget, policy_id=policy_id
    )
    async with service._uow() as uow:
        run = await uow.runs.get(run_id)
        if run is None or run["status"] in RUN_TERMINAL_STATUSES:
            return
        nodes = await uow.nodes.list(run_id)
        by_id = {n["dag_node_id"]: n for n in nodes}
        for node in nodes:
            if node["status"] == StudioNodeStatus.RUNNABLE.value or (
                node["status"] == StudioNodeStatus.DISPATCHED.value and node["task_id"] is None
            ):
                # A5: the durable envelope carries the dependency outputs the
                # worker needs to build handler inputs (frozen task IO map).
                input_refs: List[Dict[str, Any]] = []
                for dep_id in node.get("depends_on", []):
                    dep = by_id.get(dep_id)
                    if dep is not None:
                        input_refs.extend(dep.get("output_artifact_refs", []) or [])
                envelope = service._envelope(run, node, input_refs=input_refs)
                task_id = await submission.submit(envelope)
                await uow.nodes.update_node(
                    run_id,
                    node["dag_node_id"],
                    expected_version=node["version"],
                    values={
                        "status": StudioNodeStatus.DISPATCHED.value,
                        "task_id": task_id,
                    },
                )
                await service._emit(
                    uow,
                    StudioEventCatalog.TASK_SUBMITTED,
                    run_id=run_id,
                    payload={
                        "dag_node_id": node["dag_node_id"],
                        "task_type": node["task_type"],
                        "task_id": task_id,
                        "attempt": node["attempt"],
                    },
                )
        await uow.commit()


class StudioRunService(StudioRunOrchestratorPort):
    """Sole new Story orchestration authority over the durable queue."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        submission: StudioTaskSubmissionPort,
        *,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        policy_id: str = DEFAULT_APPROVAL_POLICY_ID,
    ) -> None:
        if retry_budget < 1:
            raise StudioValidationError("retry_budget must be >= 1.")
        self._session_factory = session_factory
        self._submission = submission
        self._retry_budget = retry_budget
        self._policy_id = policy_id
        self._reconciler = StudioCompletionReconciler(
            session_factory, submission, retry_budget=retry_budget, policy_id=policy_id
        )

    # -- application commands -------------------------------------------------

    async def create_series(self, command: CreateSeriesCommand) -> CreateSeriesResult:
        series_id = SeriesProjectId(_id_from_key("srs", command.idempotency_key))
        async with self._uow() as uow:
            existing = await uow.series.get(series_id)
            if existing is None:
                await uow.series.save(
                    SeriesProject(
                        series_id=series_id,
                        title=command.title,
                        description=command.description,
                        metadata={**command.metadata, "idempotency_key": command.idempotency_key},
                    )
                )
                await self._emit(
                    uow,
                    StudioEventCatalog.SERIES_CREATED,
                    aggregate_id=str(series_id),
                    payload={"title": command.title, "series_id": str(series_id)},
                )
                await uow.commit()
        return CreateSeriesResult(series_id=series_id, title=command.title)

    async def create_episode(self, command: CreateEpisodeCommand) -> CreateEpisodeResult:
        episode_id = EpisodeId(_id_from_key("ep", command.idempotency_key))
        async with self._uow() as uow:
            series = await uow.series.get(command.series_id)
            if series is None:
                raise StudioNotFoundError(
                    f"Series {command.series_id!s} does not exist.",
                    details={"series_id": str(command.series_id)},
                )
            existing = await uow.episodes.get(episode_id)
            if existing is not None:
                episode = existing
            else:
                episode = Episode(
                    episode_id=episode_id,
                    series_id=command.series_id,
                    title=command.title,
                    episode_number=command.episode_number,
                    metadata={**command.metadata, "idempotency_key": command.idempotency_key},
                )
                await uow.episodes.save(episode)
                await self._emit(
                    uow,
                    StudioEventCatalog.EPISODE_CREATED,
                    aggregate_id=str(episode_id),
                    payload={
                        "episode_id": str(episode_id),
                        "series_id": str(command.series_id),
                        "episode_number": command.episode_number,
                    },
                )
                await uow.commit()
            state = episode.state.value if isinstance(episode.state, EpisodeState) else str(episode.state)
        return CreateEpisodeResult(episode_id=episode_id, series_id=command.series_id, state=state)

    async def start_or_resume_run(self, command: StartRunCommand) -> StartRunResult:
        resume_run_id: Optional[StudioRunId] = None
        is_new_run = False
        async with self._uow() as uow:
            episode = await uow.episodes.get(command.episode_id)
            if episode is None:
                raise StudioNotFoundError(
                    f"Episode {command.episode_id!s} does not exist.",
                    details={"episode_id": str(command.episode_id)},
                )
            if episode.active_run_id is not None:
                run = await uow.runs.get(episode.active_run_id)
                if run is not None and run["status"] not in RUN_TERMINAL_STATUSES:
                    resume_run_id = run["run_id"]
                else:
                    episode = self._episode_update(episode, active_run_id=None)
                    await uow.episodes.save(episode)
                    await uow.commit()
            if resume_run_id is None:
                policy = await self._load_policy(uow)
                dag = build_story_dag(
                    episode_id=command.episode_id,
                    revision_id=episode.current_revision_id,
                    policy=policy,
                )
                run_id = StudioRunId(f"run_{uuid.uuid4().hex[:16]}")
                await uow.runs.save(
                    run_id,
                    series_id=episode.series_id,
                    episode_id=command.episode_id,
                    dag=dag,
                    status="RUNNING",
                    metadata={
                        "policy_id": policy.policy_id,
                        "policy_version": policy.policy_version,
                        "retry_budget": self._retry_budget,
                        "idempotency_key": command.idempotency_key,
                    },
                )
                await uow.nodes.upsert_nodes(run_id, initial_node_states(dag))
                episode = self._episode_update(
                    episode,
                    active_run_id=run_id,
                    awaiting_checkpoint=None,
                )
                await uow.episodes.save(episode)
                await self._emit(
                    uow,
                    StudioEventCatalog.RUN_STARTED,
                    run_id=run_id,
                    payload={
                        "episode_id": str(command.episode_id),
                        "dag_node_count": len(dag["order"]),
                        "policy_id": policy.policy_id,
                    },
                )
                await uow.commit()
                resume_run_id = run_id
                is_new_run = True
        await submit_runnable_nodes(
            self._session_factory, self._submission, resume_run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )
        return StartRunResult(
            run_id=resume_run_id,
            episode_id=command.episode_id,
            resuming=not is_new_run,
        )

    async def select_idea(self, command: SelectIdeaCommand) -> SelectIdeaResult:
        async with self._uow() as uow:
            revision = await self._revision_for_approval(
                uow, command.episode_id, command.revision_id, command.expected_optimistic_version
            )
            if command.expected_content_hash != revision.content_hash:
                raise StudioArtifactHashMismatchError(
                    "Selected idea hash does not match the canonical revision content hash.",
                    details={
                        "revision_id": str(revision.revision_id),
                        "submitted_hash": command.expected_content_hash,
                        "canonical_hash": revision.content_hash,
                    },
                )
            updated = revision.model_copy(
                update={
                    "metadata": {
                        **revision.metadata,
                        "selected_candidate_id": command.candidate_id,
                    },
                    "optimistic_version": revision.optimistic_version + 1,
                }
            )
            await uow.revisions.save(updated)
            await self._emit(
                uow,
                StudioEventCatalog.IDEA_SELECTED,
                aggregate_id=str(command.episode_id),
                revision_ref=str(revision.revision_id),
                payload={"candidate_id": command.candidate_id},
            )
            await uow.commit()
        return SelectIdeaResult(
            episode_id=command.episode_id,
            candidate_id=command.candidate_id,
            revision_id=command.revision_id,
        )

    async def derive_revision(self, command: DeriveRevisionCommand) -> DeriveRevisionResult:
        async with self._uow() as uow:
            parent = await uow.revisions.get(command.parent_revision_id)
            if parent is None:
                raise StudioNotFoundError(
                    f"Parent revision {command.parent_revision_id!s} does not exist.",
                    details={"revision_id": str(command.parent_revision_id)},
                )
            intent = (
                StudioInvalidationIntent(command.invalidation_intent)
                if command.invalidation_intent
                else None
            )
            revision = StudioRevisionService.derive_revision(
                parent=parent,
                series_id=command.series_id,
                episode_id=command.episode_id,
                new_content_hash=command.new_content_hash,
                creator=command.actor,
                actor=command.actor,
                invalidation_intent=intent,
                summary=command.summary,
                expected_parent_version=command.expected_optimistic_version,
            )
            await uow.revisions.save(revision)
            await self._emit(
                uow,
                StudioEventCatalog.REVISION_DERIVED,
                aggregate_id=str(command.episode_id),
                revision_ref=str(revision.revision_id),
                payload={"parent_revision_id": str(parent.revision_id)},
            )
            await uow.commit()
        return DeriveRevisionResult(
            revision_id=revision.revision_id,
            parent_revision_id=command.parent_revision_id,
            episode_id=command.episode_id,
        )

    async def lock_screenplay(self, command: LockScreenplayCommand) -> LockScreenplayResult:
        async with self._uow() as uow:
            revision = await self._revision_for_approval(
                uow, command.episode_id, command.revision_id, command.expected_optimistic_version
            )
            if command.expected_content_hash != revision.content_hash:
                raise StudioArtifactHashMismatchError(
                    "Lock hash does not match the canonical revision content hash.",
                    details={
                        "revision_id": str(revision.revision_id),
                        "submitted_hash": command.expected_content_hash,
                        "canonical_hash": revision.content_hash,
                    },
                )
            if revision.lock_state != StudioLockState.LOCKED:
                updated = revision.model_copy(
                    update={
                        "lock_state": StudioLockState.LOCKED,
                        "state": revision.state,
                        "optimistic_version": revision.optimistic_version + 1,
                    }
                )
                await uow.revisions.save(updated)
            episode = await uow.episodes.get(command.episode_id)
            if episode is not None and episode.state != EpisodeState.LOCKED:
                episode = self._episode_transition(episode, EpisodeState.LOCKED)
                await uow.episodes.save(episode)
            await self._emit(
                uow,
                StudioEventCatalog.SCREENPLAY_LOCKED,
                aggregate_id=str(command.episode_id),
                revision_ref=str(revision.revision_id),
                payload={},
            )
            await uow.commit()
        return LockScreenplayResult(episode_id=command.episode_id, revision_id=command.revision_id)

    async def record_approval(self, command: RecordApprovalCommand) -> RecordApprovalResult:
        approved = command.decision.upper() == ApprovalDecisionValue.APPROVED.value
        async with self._uow() as uow:
            episode = await uow.episodes.get(command.episode_id)
            if episode is None:
                raise StudioNotFoundError(
                    f"Episode {command.episode_id!s} does not exist.",
                    details={"episode_id": str(command.episode_id)},
                )
            if episode.active_run_id is None:
                raise StudioNotFoundError(
                    f"Episode {command.episode_id!s} has no active run.",
                    details={"episode_id": str(command.episode_id)},
                )
            run = await uow.runs.get(episode.active_run_id)
            if run is None:
                raise StudioNotFoundError(
                    f"Run {episode.active_run_id!s} does not exist.",
                    details={"run_id": str(episode.active_run_id)},
                )
            nodes = await uow.nodes.list(run["run_id"])
            waiting = [
                n
                for n in nodes
                if n.get("checkpoint") == command.checkpoint
                and n["status"] == StudioNodeStatus.WAITING_APPROVAL.value
            ]
            if not waiting:
                raise StudioNotFoundError(
                    f"No node of run {run['run_id']!s} is awaiting approval at "
                    f"checkpoint {command.checkpoint!r}.",
                    details={"run_id": str(run["run_id"]), "checkpoint": command.checkpoint},
                )
            target = waiting[0]
            revision = await self._revision_for_approval(
                uow, command.episode_id, command.revision_id, command.expected_optimistic_version
            )
            policy = await self._load_policy(uow)
            decision = ApprovalPolicyService.record_decision(
                policy=policy,
                revision=revision,
                aggregate_id=command.episode_id,
                checkpoint=ApprovalCheckpoint(command.checkpoint),
                actor=command.actor,
                decision=ApprovalDecisionValue(command.decision),
                reason=command.reason,
                submitted_artifact_hash=command.artifact_hash,
                expected_optimistic_version=command.expected_optimistic_version,
            )
            await uow.approvals.record_decision(decision)
            if approved:
                await uow.nodes.update_node(
                    run["run_id"],
                    target["dag_node_id"],
                    expected_version=target["version"],
                    values={"status": StudioNodeStatus.SUCCEEDED.value},
                )
                await self._emit(
                    uow,
                    StudioEventCatalog.APPROVAL_RECORDED,
                    run_id=run["run_id"],
                    aggregate_id=str(command.episode_id),
                    revision_ref=str(revision.revision_id),
                    payload={
                        "checkpoint": command.checkpoint,
                        "decision": decision.decision.value,
                        "actor": command.actor,
                    },
                )
                if command.checkpoint == ApprovalCheckpoint.SCREENPLAY.value:
                    episode = self._episode_transition(episode, EpisodeState.LOCKED)
                    await self._emit(
                        uow,
                        StudioEventCatalog.SCREENPLAY_LOCKED,
                        run_id=run["run_id"],
                        aggregate_id=str(command.episode_id),
                        revision_ref=str(revision.revision_id),
                        payload={},
                    )
                else:
                    episode = self._episode_update(episode, awaiting_checkpoint=None)
                await uow.episodes.save(episode)
                fresh_nodes = await uow.nodes.list(run["run_id"])
                await self._advance_dependents(uow, run["run_id"], fresh_nodes)
                await uow.commit()
            else:
                await uow.nodes.update_node(
                    run["run_id"],
                    target["dag_node_id"],
                    expected_version=target["version"],
                    values={"status": StudioNodeStatus.FAILED.value, "error": command.reason},
                )
                await self._emit(
                    uow,
                    StudioEventCatalog.APPROVAL_RECORDED,
                    run_id=run["run_id"],
                    aggregate_id=str(command.episode_id),
                    revision_ref=str(revision.revision_id),
                    payload={
                        "checkpoint": command.checkpoint,
                        "decision": decision.decision.value,
                        "actor": command.actor,
                    },
                )
                await self._finish_run_failed(uow, run["run_id"], episode, command.reason)
                await uow.commit()
        if approved:
            await self._submit_runnable_nodes(run["run_id"])
        return RecordApprovalResult(
            episode_id=command.episode_id,
            checkpoint=command.checkpoint,
            next_state=(
                EpisodeState.LOCKED.value
                if approved and command.checkpoint == ApprovalCheckpoint.SCREENPLAY.value
                else None
            ),
            awaiting_approval=not approved,
        )

    async def cancel_run(self, run_id: StudioRunId, actor: str, reason: str = "") -> Dict[str, Any]:
        async with self._uow() as uow:
            run = await uow.runs.get(run_id)
            if run is None:
                raise StudioNotFoundError(
                    f"Run {run_id!s} does not exist.", details={"run_id": str(run_id)}
                )
            if run["status"] in RUN_TERMINAL_STATUSES:
                return {"run_id": str(run_id), "status": run["status"], "cancelled": False}
            nodes = await uow.nodes.list(run_id)
            for node in nodes:
                if node["status"] not in StudioNodeStatus.terminal():
                    await uow.nodes.update_node(
                        run_id,
                        node["dag_node_id"],
                        expected_version=node["version"],
                        values={
                            "status": StudioNodeStatus.CANCELLED.value,
                            "error": reason or f"cancelled by {actor}",
                        },
                    )
            await uow.runs.save(
                run_id,
                series_id=run["series_id"],
                episode_id=run["episode_id"],
                dag=run["dag"],
                status="CANCELLED",
                metadata={**run.get("metadata", {}), "cancelled_by": actor, "cancel_reason": reason},
            )
            episode = await uow.episodes.get(run["episode_id"])
            if episode is not None and not EpisodeStateMachine.is_terminal(episode.state):
                next_state = EpisodeStateMachine.transition(episode.state, EpisodeState.CANCELLED)
                episode = self._episode_update(
                    episode,
                    state=next_state,
                    active_run_id=None,
                    awaiting_checkpoint=None,
                )
                await uow.episodes.save(episode)
            await self._emit(
                uow,
                StudioEventCatalog.RUN_CANCELLED,
                run_id=run_id,
                payload={"actor": actor, "reason": reason},
            )
            await uow.commit()
        return {"run_id": str(run_id), "status": "CANCELLED", "cancelled": True}

    async def reconcile(self, result: StudioTaskResult) -> Dict[str, Any]:
        """Durable-completion entry point; the ONLY DAG-advancing path."""
        return await self._reconciler.handle_task_result(result)

    # -- internal helpers ------------------------------------------------------

    @asynccontextmanager
    async def _uow(self) -> AsyncIterator[StudioUnitOfWork]:
        uow = StudioUnitOfWork(self._session_factory)
        await uow.__aenter__()
        try:
            yield uow
        except BaseException:
            await uow.__aexit__(*sys.exc_info())
            raise
        await uow.__aexit__(None, None, None)

    async def _load_policy(self, uow: StudioUnitOfWork) -> ApprovalPolicy:
        policy = await uow.approvals.get_policy(self._policy_id)
        if policy is None:
            return ApprovalPolicy(policy_id=self._policy_id, policy_version="1")
        return policy

    def _envelope(
        self,
        run: Dict[str, Any],
        node: Dict[str, Any],
        *,
        input_refs: Optional[List[Dict[str, Any]]] = None,
    ) -> StudioTaskEnvelope:
        return StudioTaskEnvelope(
            task_type=StudioTaskType(node["task_type"]),
            studio_run_id=StudioRunId(run["run_id"]),
            dag_node_id=node["dag_node_id"],
            series_id=SeriesProjectId(run["series_id"]),
            episode_id=EpisodeId(run["episode_id"]),
            revision_id=(
                ProductionRevisionId(run["dag"].get("revision_id"))
                if run["dag"].get("revision_id")
                else None
            ),
            input_artifact_refs=[StudioArtifactRef(**ref) for ref in (input_refs or [])],
            input_hashes=list(node.get("input_hashes", [])),
            idempotency_key=f"{run['run_id']}:{node['dag_node_id']}:{node['attempt']}",
            attempt=node["attempt"],
            payload={},
        )

    async def _submit_runnable_nodes(self, run_id: StudioRunId) -> None:
        """Durable dispatch: queue commit first, node identity second."""
        await submit_runnable_nodes(
            self._session_factory, self._submission, run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )

    async def _advance_dependents(
        self, uow: StudioUnitOfWork, run_id: StudioRunId, nodes: List[Dict[str, Any]]
    ) -> bool:
        """Mark PENDING nodes whose dependencies are terminal as RUNNABLE."""
        by_id = {n["dag_node_id"]: n for n in nodes}
        changed = False
        for node in nodes:
            if (
                node["status"] == StudioNodeStatus.PENDING.value
                and dependencies_terminal(node, by_id)
            ):
                await uow.nodes.update_node(
                    run_id,
                    node["dag_node_id"],
                    expected_version=node["version"],
                    values={"status": StudioNodeStatus.RUNNABLE.value},
                )
                changed = True
        return changed

    @staticmethod
    async def _finish_run_failed(
        uow: StudioUnitOfWork,
        run_id: StudioRunId,
        episode: Episode,
        reason: str,
    ) -> None:
        run = await uow.runs.get(run_id)
        if run is None or run["status"] in RUN_TERMINAL_STATUSES:
            return
        await uow.runs.save(
            run_id,
            series_id=run["series_id"],
            episode_id=run["episode_id"],
            dag=run["dag"],
            status="FAILED",
            metadata={**run.get("metadata", {}), "failure_reason": reason},
        )
        if not EpisodeStateMachine.is_terminal(episode.state):
            episode = StudioRunService._episode_transition(episode, EpisodeState.FAILED)
            await uow.episodes.save(episode)
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.RUN_FAILED,
            run_id=run_id,
            payload={"episode_id": str(episode.episode_id), "reason": reason},
        )

    async def _revision_for_approval(
        self,
        uow: StudioUnitOfWork,
        episode_id: EpisodeId,
        revision_id: ProductionRevisionId,
        expected_version: Optional[int],
    ) -> Any:
        revision = await uow.revisions.get(revision_id)
        if revision is None:
            raise StudioNotFoundError(
                f"Revision {revision_id!s} does not exist.",
                details={"revision_id": str(revision_id)},
            )
        if expected_version is not None and revision.optimistic_version != expected_version:
            from windagent_core.contracts.studio.errors import StudioStaleRevisionError

            raise StudioStaleRevisionError(
                f"Revision {revision_id!s} version mismatch: expected "
                f"{expected_version}, current {revision.optimistic_version}.",
                details={
                    "revision_id": str(revision_id),
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        return revision

    @staticmethod
    def _episode_update(episode: Episode, **updates: Any) -> Episode:
        return episode.model_copy(
            update={
                **updates,
                "updated_at": utc_now(),
                "optimistic_version": episode.optimistic_version + 1,
            }
        )

    @classmethod
    def _episode_transition(cls, episode: Episode, target: EpisodeState) -> Episode:
        if episode.state == target:
            return episode
        next_state = EpisodeStateMachine.transition(episode.state, target)
        return cls._episode_update(episode, state=next_state)

    @staticmethod
    async def _emit(
        uow: StudioUnitOfWork,
        event_type: str,
        *,
        run_id: Optional[StudioRunId] = None,
        aggregate_id: Optional[str] = None,
        revision_ref: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        envelope = StudioEventEnvelope(
            event_type=event_type,
            aggregate_id=aggregate_id or (str(run_id) if run_id else "studio"),
            studio_run_id=run_id,
            revision_ref=revision_ref,
            payload=payload or {},
        )
        await uow.append_event(envelope)
        await uow.publish_outbox(envelope)


class StudioCompletionReconciler:
    """Consumes durable task final state and advances the DAG only through it."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        submission: StudioTaskSubmissionPort,
        *,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        policy_id: str = DEFAULT_APPROVAL_POLICY_ID,
    ) -> None:
        self._session_factory = session_factory
        self._submission = submission
        self._retry_budget = retry_budget
        self._policy_id = policy_id

    async def handle_task_result(self, result: StudioTaskResult) -> Dict[str, Any]:
        """Apply one durable task result; advance the DAG; submit new work.

        Returns a correlation dict; raises on stale/unknown completions.
        """
        async with StudioUnitOfWork(self._session_factory) as uow:
            run = await uow.runs.get(result.studio_run_id)
            if run is None:
                raise StudioNotFoundError(
                    f"Completion for unknown run {result.studio_run_id!s}.",
                    details={"run_id": str(result.studio_run_id), "task_id": result.task_id},
                )
            if run["status"] in RUN_TERMINAL_STATUSES:
                return {
                    "run_id": str(result.studio_run_id),
                    "dag_node_id": result.dag_node_id,
                    "duplicate": True,
                    "reason": "run already terminal",
                }
            node = await uow.nodes.get_by_task_id(result.task_id)
            if node is None:
                raise StudioStaleNodeError(
                    f"Stale completion: task {result.task_id!r} is not bound to any "
                    f"dispatched node of run {result.studio_run_id!s}.",
                    details={
                        "run_id": str(result.studio_run_id),
                        "task_id": result.task_id,
                        "dag_node_id": result.dag_node_id,
                    },
                )
            if node["task_id"] != result.task_id:
                raise StudioStaleNodeError(
                    f"Stale completion: node {node['dag_node_id']!r} was re-dispatched "
                    f"with a newer task identity.",
                    details={
                        "dag_node_id": node["dag_node_id"],
                        "expected_task_id": node["task_id"],
                        "received_task_id": result.task_id,
                    },
                )
            if node["status"] in (
                StudioNodeStatus.SUCCEEDED.value,
                StudioNodeStatus.FAILED.value,
                StudioNodeStatus.CANCELLED.value,
                StudioNodeStatus.WAITING_APPROVAL.value,
            ):
                return {
                    "run_id": str(result.studio_run_id),
                    "dag_node_id": node["dag_node_id"],
                    "duplicate": True,
                    "reason": f"node already {node['status']}",
                }

            if result.status == StudioTaskStatus.SUCCEEDED:
                await self._on_succeeded(uow, run, node, result)
            elif result.status == StudioTaskStatus.FAILED:
                await self._on_failed(uow, run, node, result)
            elif result.status == StudioTaskStatus.CANCELLED:
                await uow.nodes.update_node(
                    run["run_id"],
                    node["dag_node_id"],
                    expected_version=node["version"],
                    values={
                        "status": StudioNodeStatus.CANCELLED.value,
                        "error": result.error,
                    },
                )
            else:
                raise StudioValidationError(
                    f"Unhandled task status {result.status.value!r}.",
                    details={"task_id": result.task_id},
                )

            nodes = await uow.nodes.list(run["run_id"])
            await self._advance_and_finish(uow, run, nodes)
            await uow.commit()
        await self._service_submit(run["run_id"])
        return {"run_id": str(run["run_id"]), "dag_node_id": node["dag_node_id"], "duplicate": False}

    async def _on_succeeded(
        self,
        uow: StudioUnitOfWork,
        run: Dict[str, Any],
        node: Dict[str, Any],
        result: StudioTaskResult,
    ) -> None:
        output_hashes = list(result.output_hashes)
        output_refs = [r.model_dump() for r in result.output_artifact_refs]
        gate = bool(node.get("gate", False))
        checkpoint = node.get("checkpoint")
        if gate and checkpoint:
            await uow.nodes.update_node(
                run["run_id"],
                node["dag_node_id"],
                expected_version=node["version"],
                values={
                    "status": StudioNodeStatus.WAITING_APPROVAL.value,
                    "output_hashes": output_hashes,
                    "output_artifact_refs": output_refs,
                },
            )
            episode = await uow.episodes.get(run["episode_id"])
            if episode is not None:
                review_state = CHECKPOINT_TO_REVIEW_STATE[ApprovalCheckpoint(checkpoint)]
                if episode.state != review_state:
                    next_state = EpisodeStateMachine.transition(episode.state, review_state)
                    episode = StudioRunService._episode_update(
                        episode, state=next_state, awaiting_checkpoint=checkpoint
                    )
                else:
                    episode = StudioRunService._episode_update(episode, awaiting_checkpoint=checkpoint)
                await uow.episodes.save(episode)
            await StudioRunService._emit(
                uow,
                StudioEventCatalog.APPROVAL_REQUESTED,
                run_id=run["run_id"],
                aggregate_id=str(run["episode_id"]),
                revision_ref=run["dag"].get("revision_id"),
                payload={"checkpoint": checkpoint, "dag_node_id": node["dag_node_id"]},
            )
        else:
            await uow.nodes.update_node(
                run["run_id"],
                node["dag_node_id"],
                expected_version=node["version"],
                values={
                    "status": StudioNodeStatus.SUCCEEDED.value,
                    "output_hashes": output_hashes,
                    "output_artifact_refs": output_refs,
                },
            )
            if checkpoint:
                episode = await uow.episodes.get(run["episode_id"])
                if episode is not None:
                    review_state = CHECKPOINT_TO_REVIEW_STATE[ApprovalCheckpoint(checkpoint)]
                    if episode.state != review_state:
                        episode = StudioRunService._episode_transition(episode, review_state)
                        await uow.episodes.save(episode)
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.TASK_COMPLETED,
            run_id=run["run_id"],
            aggregate_id=str(run["episode_id"]),
            revision_ref=run["dag"].get("revision_id"),
            payload={
                "dag_node_id": node["dag_node_id"],
                "task_id": result.task_id,
                "status": result.status.value,
                "output_hashes": output_hashes,
            },
        )

    async def _on_failed(
        self,
        uow: StudioUnitOfWork,
        run: Dict[str, Any],
        node: Dict[str, Any],
        result: StudioTaskResult,
    ) -> None:
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.TASK_COMPLETED,
            run_id=run["run_id"],
            aggregate_id=str(run["episode_id"]),
            revision_ref=run["dag"].get("revision_id"),
            payload={
                "dag_node_id": node["dag_node_id"],
                "task_id": result.task_id,
                "status": result.status.value,
                "error": result.error,
            },
        )
        if node["attempt"] < self._retry_budget:
            # Park for re-dispatch: task identity cleared, attempt bumped. The
            # post-commit submission loop issues the fresh (run, node, attempt)
            # envelope with a NEW idempotency key, so the retry is durable and
            # the failed attempt's key never collides.
            await uow.nodes.update_node(
                run["run_id"],
                node["dag_node_id"],
                expected_version=node["version"],
                values={
                    "status": StudioNodeStatus.DISPATCHED.value,
                    "task_id": None,
                    "attempt": node["attempt"] + 1,
                    "error": result.error,
                },
            )
        else:
            await uow.nodes.update_node(
                run["run_id"],
                node["dag_node_id"],
                expected_version=node["version"],
                values={
                    "status": StudioNodeStatus.FAILED.value,
                    "error": result.error,
                },
            )

    async def _advance_and_finish(
        self,
        uow: StudioUnitOfWork,
        run: Dict[str, Any],
        nodes: List[Dict[str, Any]],
    ) -> None:
        by_id = {n["dag_node_id"]: n for n in nodes}
        run_id = run["run_id"]
        for node in nodes:
            if (
                node["status"] == StudioNodeStatus.PENDING.value
                and dependencies_terminal(node, by_id)
            ):
                await uow.nodes.update_node(
                    run_id,
                    node["dag_node_id"],
                    expected_version=node["version"],
                    values={"status": StudioNodeStatus.RUNNABLE.value},
                )
        if run["status"] in RUN_TERMINAL_STATUSES:
            return
        fresh = await uow.nodes.list(run_id)
        statuses = {n["status"] for n in fresh}
        episode = await uow.episodes.get(run["episode_id"])
        if (
            StudioNodeStatus.FAILED.value in statuses
            or StudioNodeStatus.CANCELLED.value in statuses
        ):
            reason = next(
                (
                    n.get("error") or "node failed"
                    for n in fresh
                    if n["status"] != StudioNodeStatus.SUCCEEDED.value
                ),
                "run failed",
            )
            await StudioRunService._finish_run_failed(uow, run_id, episode, reason)
            return
        all_terminal = statuses and statuses <= StudioNodeStatus.terminal()
        if not all_terminal:
            return
        # All nodes succeeded: lock the screenplay and finish the run.
        await uow.runs.save(
            run_id,
            series_id=run["series_id"],
            episode_id=run["episode_id"],
            dag=run["dag"],
            status="COMPLETED",
            metadata=run.get("metadata", {}),
        )
        if episode is not None:
            if episode.state != EpisodeState.LOCKED:
                episode = StudioRunService._episode_transition(episode, EpisodeState.LOCKED)
                await uow.episodes.save(episode)
                await StudioRunService._emit(
                    uow,
                    StudioEventCatalog.SCREENPLAY_LOCKED,
                    run_id=run_id,
                    aggregate_id=str(episode.episode_id),
                    revision_ref=run["dag"].get("revision_id"),
                    payload={},
                )
            episode = StudioRunService._episode_transition(episode, EpisodeState.READY_FOR_PRODUCTION)
            await uow.episodes.save(episode)
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.EPISODE_READY_FOR_PRODUCTION,
            run_id=run_id,
            aggregate_id=str(run["episode_id"]),
            revision_ref=run["dag"].get("revision_id"),
            payload={},
        )
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.RUN_COMPLETED,
            run_id=run_id,
            payload={"episode_id": str(run["episode_id"])},
        )

    async def _service_submit(self, run_id: StudioRunId) -> None:
        await submit_runnable_nodes(
            self._session_factory, self._submission, run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )


__all__ = ["StudioRunService", "StudioCompletionReconciler"]
