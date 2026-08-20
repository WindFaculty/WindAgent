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
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

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
    StudioIdempotencyMismatchError,
    StudioNotFoundError,
    StudioStaleNodeError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
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
from windagent_core.contracts.repositories.unit_of_work import (
    StudioUnitOfWorkFactory,
    StudioUnitOfWorkPort,
)
from windagent_core.contracts.studio.ports import (
    StudioRunOrchestratorPort,
    StudioTaskSubmissionPort,
)
from windagent_core.config.certification import certification_mode_enabled
from windagent_core.domain.studio.approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyService,
)
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
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
    StudioProductionRevision,
    StudioRevisionService,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.domain.story.ideation.models import IdeaCandidateSet, SelectedIdea
from windagent_core.domain.story.ids import (
    LockedScreenplayReceiptId,
    SelectedIdeaId,
)
from windagent_core.domain.story.review import (
    REQUIRED_PACKAGE_ARTIFACTS,
    LockedScreenplayReceipt,
    ReviewReport,
)
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_core.domain.story.validation import ValidationSeverity
from windagent_core.events.studio import StudioEventCatalog, StudioEventEnvelope
from windagent_orchestration.studio.dag import (
    NODE_REVIEW,
    NODE_REVIEW_REVISED,
    NODE_REVISE,
    build_story_dag,
    dependencies_terminal,
    initial_node_states,
)

# The Studio UoW is injected as a zero-argument factory by a composition root.
# The orchestration layer stays ORM-free (architecture checker forbids
# sqlalchemy/storage imports); it only ever sees the core ``StudioUnitOfWorkPort``.

DEFAULT_APPROVAL_POLICY_ID = "studio.default"
DEFAULT_RETRY_BUDGET = 3
RUN_TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "FAILED", "CANCELLED", "REVISION_REQUIRED"}
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


#: Default per-run execution budget. The worker fails any task whose envelope
#: deadline is reached, so a slow/hung provider can never leave a run in
#: RUNNING past its authoritative deadline (C7 attempt-8 forensic finding).
RUN_DEADLINE_SECONDS_DEFAULT = 2700


def run_deadline(run: Dict[str, Any]) -> datetime:
    """Absolute deadline for every task of ``run``: run start + budget.

    Run-relative (not per-task): a chain of slow tasks can never outlive the
    run deadline, because each envelope carries the SAME absolute deadline and
    the worker fails any task that would cross it.
    """
    budget = int(
        os.getenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", RUN_DEADLINE_SECONDS_DEFAULT)
    )
    created = run.get("created_at") or utc_now()
    return created + timedelta(seconds=max(1, budget))


def _id_from_key(prefix: str, idempotency_key: str) -> str:
    """Deterministic aggregate id from an idempotency key (repeat == same id)."""
    return f"{prefix}_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]}"


async def submit_runnable_nodes(
    uow_factory: StudioUnitOfWorkFactory,
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
        uow_factory, submission, retry_budget=retry_budget, policy_id=policy_id
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
                # Full-DAG auto-drive (C7, B9 co-signed A-side half): the
                # orchestrator completes the inputs/payload the frozen task map
                # requires but the DAG edges cannot carry — SelectedIdea for
                # bible.generate (selection replay) and the A-issued receipt
                # for studio.story.lock. Purely core-domain logic; nothing is
                # invented or faked, the worker still executes every handler.
                augmented = await service._augment_node_inputs(uow, run, node, input_refs)
                input_refs = augmented["input_refs"]
                envelope = service._envelope(
                    run, node, input_refs=input_refs, payload=augmented["payload"]
                )
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
        uow_factory: StudioUnitOfWorkFactory,
        submission: StudioTaskSubmissionPort,
        *,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        policy_id: str = DEFAULT_APPROVAL_POLICY_ID,
    ) -> None:
        if retry_budget < 1:
            raise StudioValidationError("retry_budget must be >= 1.")
        self._uow_factory = uow_factory
        self._submission = submission
        self._retry_budget = retry_budget
        self._policy_id = policy_id
        self._reconciler = StudioCompletionReconciler(
            uow_factory, submission, retry_budget=retry_budget, policy_id=policy_id
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
                if episode.current_revision_id is None:
                    # Full-DAG auto-drive (C7): a fresh episode has no revision,
                    # but every Story run is bound to one (select/approve/lock
                    # commands are revision-scoped). Seed revision 1 from the
                    # episode's stable identity before the DAG is built.
                    seeded = self._seed_initial_revision(episode)
                    await uow.revisions.save(seeded)
                    episode = episode.attach_revision(seeded.revision_id)
                    await uow.episodes.save(episode)
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
            self._uow_factory, self._submission, resume_run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )
        return StartRunResult(
            run_id=resume_run_id,
            episode_id=command.episode_id,
            resuming=not is_new_run,
        )

    async def select_idea(self, command: SelectIdeaCommand) -> SelectIdeaResult:
        async with self._uow() as uow:
            existing = await uow.revisions.get(command.revision_id)
            if existing is None:
                raise StudioNotFoundError(
                    f"Revision {command.revision_id!s} does not exist.",
                    details={"revision_id": str(command.revision_id)},
                )
            selection_key = existing.metadata.get("idea_selection_idempotency_key")
            if selection_key == command.idempotency_key:
                matches = (
                    existing.metadata.get("selected_candidate_id") == command.candidate_id
                    and existing.metadata.get("idea_selection_content_hash")
                    == command.expected_content_hash
                    and existing.metadata.get("idea_selection_base_version")
                    == command.expected_optimistic_version
                )
                if not matches:
                    raise StudioIdempotencyMismatchError(
                        "Repeated idea-selection key used with a different request.",
                        details={"idempotency_key": command.idempotency_key},
                    )
                return SelectIdeaResult(
                    episode_id=command.episode_id,
                    candidate_id=command.candidate_id,
                    revision_id=command.revision_id,
                    content_hash=existing.content_hash,
                    optimistic_version=existing.optimistic_version,
                    replayed=True,
                )
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
                        "idea_selection_idempotency_key": command.idempotency_key,
                        "idea_selection_content_hash": command.expected_content_hash,
                        "idea_selection_base_version": command.expected_optimistic_version,
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
            content_hash=updated.content_hash,
            optimistic_version=updated.optimistic_version,
        )

    async def derive_revision(self, command: DeriveRevisionCommand) -> DeriveRevisionResult:
        async with self._uow() as uow:
            parent = await uow.revisions.get(command.parent_revision_id)
            if parent is None:
                raise StudioNotFoundError(
                    f"Parent revision {command.parent_revision_id!s} does not exist.",
                    details={"revision_id": str(command.parent_revision_id)},
                )
            source_artifact: Optional[StoryArtifactEnvelope] = None
            if certification_mode_enabled():
                source_artifact = next(
                    (
                        artifact
                        for artifact in await uow.artifacts.list_for_episode(
                            command.episode_id
                        )
                        if artifact.artifact_type.value == "ScreenplayDraft"
                        and artifact.content_hash == command.new_content_hash
                    ),
                    None,
                )
                if source_artifact is None:
                    raise StudioValidationError(
                        "Certification revision hash must bind a persisted "
                        "canonical ScreenplayDraft artifact.",
                        details={
                            "episode_id": str(command.episode_id),
                            "content_hash": command.new_content_hash,
                        },
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
            if source_artifact is not None:
                revision = revision.model_copy(
                    update={
                        "metadata": {
                            **revision.metadata,
                            "source_screenplay_artifact_id": str(
                                source_artifact.artifact_id
                            ),
                        }
                    }
                )
            await uow.revisions.save(revision)
            # Full-DAG auto-drive (C7): a derived revision becomes the
            # episode's current revision so the next run regenerates under it.
            # Locked episodes stay locked (derive-after-lock is a separate
            # read-only path; a new run there is rejected by the lifecycle).
            episode = await uow.episodes.get(command.episode_id)
            if episode is not None and not episode.is_locked:
                episode = episode.attach_revision(revision.revision_id)
                await uow.episodes.save(episode)
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
        submit_after_commit = approved
        next_state: Optional[str] = None
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
            review_report: Optional[ReviewReport] = None
            if command.checkpoint == ApprovalCheckpoint.SCREENPLAY.value:
                review_report = await self._review_report_for_gate(uow, target)
                if approved and not review_report.is_pass:
                    raise StudioValidationError(
                        "A screenplay with blocking review findings cannot be approved.",
                        details={"review_report_id": str(review_report.report_id)},
                    )
                if not approved:
                    self._require_policy_revision_finding(policy, review_report)
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
                episode = self._episode_update(episode, awaiting_checkpoint=None)
                if target["dag_node_id"] == NODE_REVIEW:
                    for branch_node_id in (NODE_REVISE, NODE_REVIEW_REVISED):
                        branch = next(
                            n for n in nodes if n["dag_node_id"] == branch_node_id
                        )
                        if branch["status"] == StudioNodeStatus.PENDING.value:
                            await uow.nodes.update_node(
                                run["run_id"],
                                branch_node_id,
                                expected_version=branch["version"],
                                values={
                                    "status": StudioNodeStatus.SKIPPED.value,
                                    "error": "quality_revision_branch_not_required",
                                },
                            )
                await uow.episodes.save(episode)
                fresh_nodes = await uow.nodes.list(run["run_id"])
                await self._advance_dependents(uow, run["run_id"], fresh_nodes)
                await uow.commit()
            else:
                await uow.nodes.update_node(
                    run["run_id"],
                    target["dag_node_id"],
                    expected_version=target["version"],
                    values={
                        "status": (
                            StudioNodeStatus.SUCCEEDED.value
                            if command.checkpoint
                            == ApprovalCheckpoint.SCREENPLAY.value
                            else StudioNodeStatus.FAILED.value
                        ),
                        "error": command.reason,
                    },
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
                if command.checkpoint != ApprovalCheckpoint.SCREENPLAY.value:
                    await self._finish_run_failed(uow, run["run_id"], episode, command.reason)
                    next_state = EpisodeState.FAILED.value
                else:
                    assert review_report is not None
                    revising_state = (
                        episode.state
                        if episode.state == EpisodeState.REVISING
                        else EpisodeStateMachine.transition(
                            episode.state, EpisodeState.REVISING
                        )
                    )
                    episode = self._episode_update(
                        episode,
                        state=revising_state,
                        awaiting_checkpoint=None,
                    )
                    await uow.episodes.save(episode)
                    next_state = EpisodeState.REVISING.value
                    await self._emit(
                        uow,
                        StudioEventCatalog.STORY_REVISION_REQUESTED,
                        run_id=run["run_id"],
                        aggregate_id=str(command.episode_id),
                        revision_ref=str(revision.revision_id),
                        payload={
                            "review_report_id": str(review_report.report_id),
                            "draft_id": str(review_report.draft_id),
                            "review_iteration": review_report.review_iteration,
                            "finding_codes": [
                                finding.code
                                for finding in review_report.blocking_findings
                            ],
                            "reason": command.reason,
                        },
                    )
                    if target["dag_node_id"] == NODE_REVIEW:
                        fresh_nodes = await uow.nodes.list(run["run_id"])
                        await self._advance_dependents(uow, run["run_id"], fresh_nodes)
                        submit_after_commit = True
                    else:
                        await uow.runs.save(
                            run["run_id"],
                            series_id=run["series_id"],
                            episode_id=run["episode_id"],
                            dag=run["dag"],
                            status="REVISION_REQUIRED",
                            metadata={
                                **run.get("metadata", {}),
                                "revision_required": {
                                    "review_report_id": str(review_report.report_id),
                                    "review_iteration": review_report.review_iteration,
                                    "reason": command.reason,
                                },
                            },
                        )
                await uow.commit()
        if submit_after_commit:
            await self._submit_runnable_nodes(run["run_id"])
        return RecordApprovalResult(
            episode_id=command.episode_id,
            checkpoint=command.checkpoint,
            next_state=next_state,
            awaiting_approval=(
                not approved
                and command.checkpoint != ApprovalCheckpoint.SCREENPLAY.value
            ),
        )

    @staticmethod
    async def _review_report_for_gate(
        uow: StudioUnitOfWorkPort, target: Dict[str, Any]
    ) -> ReviewReport:
        report_ref = next(
            (
                ref
                for ref in target.get("output_artifact_refs", []) or []
                if ref["artifact_type"] == "ReviewReport"
            ),
            None,
        )
        if report_ref is None:
            raise StudioValidationError(
                "A screenplay approval gate must reference its persisted ReviewReport."
            )
        artifact = await uow.artifacts.get(ArtifactId(report_ref["artifact_id"]))
        if artifact is None:
            raise StudioValidationError(
                "The screenplay ReviewReport is missing.",
                details={"artifact_id": str(report_ref["artifact_id"])},
            )
        report = ReviewReport.model_validate(artifact.content)
        if artifact.content_hash != report_ref["content_hash"]:
            raise StudioValidationError(
                "The screenplay ReviewReport reference does not match persisted authority.",
                details={"artifact_id": str(report_ref["artifact_id"])},
            )
        return report

    @staticmethod
    def _require_policy_revision_finding(
        policy: ApprovalPolicy, report: ReviewReport
    ) -> None:
        threshold = policy.quality_threshold_for(ApprovalCheckpoint.SCREENPLAY)
        qualifying = [
            finding
            for finding in report.findings
            if finding.code == "QUALITY_THRESHOLD_VIOLATION"
            and finding.severity == ValidationSeverity.BLOCKING
            and finding.threshold == threshold
            and finding.actual_score is not None
            and threshold is not None
            and finding.actual_score < threshold
            and finding.source == "model"
            and finding.provenance
        ]
        if report.verdict != "REVIEW_REQUIRED" or not qualifying:
            raise StudioValidationError(
                "Revision requires a genuine blocking policy-threshold finding.",
                details={
                    "review_report_id": str(report.report_id),
                    "verdict": report.verdict,
                    "policy_threshold": threshold,
                },
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
    async def _uow(self) -> AsyncIterator[StudioUnitOfWorkPort]:
        uow = self._uow_factory()
        await uow.__aenter__()
        try:
            yield uow
        except BaseException:
            await uow.__aexit__(*sys.exc_info())
            raise
        await uow.__aexit__(None, None, None)

    async def _load_policy(self, uow: StudioUnitOfWorkPort) -> ApprovalPolicy:
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
        payload: Optional[Dict[str, Any]] = None,
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
            deadline=run_deadline(run),
            payload=payload or {},
        )

    # -- full-DAG auto-drive (C7) ------------------------------------------

    @staticmethod
    def _seed_initial_revision(episode: Episode) -> Any:
        """Revision 1 for a fresh episode: deterministic id + content hash.

        The content hash is derived from the episode's stable identity and
        brief metadata, so select/approve/lock commands can bind to it without
        any client-supplied value (the server is the authority).
        """
        identity = hashlib.sha256(
            (
                f"{episode.episode_id}|{episode.series_id}|{episode.title}|"
                f"{episode.episode_number}|{episode.metadata}"
            ).encode("utf-8")
        ).hexdigest()
        return StudioProductionRevision(
            revision_id=ProductionRevisionId(f"rev_{episode.episode_id.value}_1"),
            series_id=episode.series_id,
            episode_id=episode.episode_id,
            creator="orchestrator:auto-seed",
            actor="orchestrator:auto-seed",
            content_hash=identity,
            metadata={"seeded_by": "orchestrator:auto-seed", "seed": "episode-identity"},
        )

    async def _augment_node_inputs(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        node: Dict[str, Any],
        input_refs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Complete frozen-task inputs/payload the DAG edges cannot carry.

        Returns ``{"input_refs": [...], "payload": {...}}``. Fail-open here is
        deliberate: missing context still reaches the worker, which fails
        closed with the typed taxonomy (STUDIO_INPUT_ARTIFACT_MISSING).
        """
        task_type = node["task_type"]
        payload: Dict[str, Any] = {}
        if task_type == StudioTaskType.BIBLE_GENERATE.value:
            input_refs = await self._inject_selected_idea(uow, run, input_refs)
        elif task_type == StudioTaskType.OUTLINE_GENERATE.value:
            input_refs = await self._inject_run_artifacts(
                uow,
                run,
                input_refs,
                {"CharacterCanon", "WorldBible"},
            )
        elif task_type == StudioTaskType.SCREENPLAY_GENERATE.value:
            input_refs = await self._inject_run_artifacts(
                uow,
                run,
                input_refs,
                {"BeatSheet", "CharacterCanon", "WorldBible"},
            )
        elif task_type == StudioTaskType.REVIEW.value:
            policy = await self._load_policy(uow)
            payload = {
                "quality_threshold": policy.quality_threshold_for(
                    ApprovalCheckpoint.SCREENPLAY
                ),
                "maximum_iterations": policy.max_review_revision_iterations,
                "review_iteration": (
                    2 if node["dag_node_id"] == NODE_REVIEW_REVISED else 1
                ),
            }
        elif task_type == StudioTaskType.REVISE.value:
            input_refs = await self._inject_reviewed_draft(uow, run, input_refs)
        elif task_type == StudioTaskType.LOCK.value:
            input_refs, payload = await self._lock_inputs(uow, run, input_refs)
        return {"input_refs": input_refs, "payload": payload}

    @staticmethod
    async def _inject_run_artifacts(
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        input_refs: List[Dict[str, Any]],
        artifact_types: set[str],
    ) -> List[Dict[str, Any]]:
        """Attach exact upstream artifacts already produced by this run.

        Linear DAG edges carry only the immediate predecessor's outputs. Some
        handlers also need earlier canon/structure artifacts for deterministic
        cross-validation. Those refs must come from this run's durable nodes;
        never from a latest-artifact lookup across revisions or episodes.
        """
        present = {ref["artifact_type"] for ref in input_refs}
        wanted = artifact_types - present
        if not wanted:
            return input_refs
        nodes = await uow.nodes.list(run["run_id"])
        additions: List[Dict[str, Any]] = []
        for node in nodes:
            for ref in node.get("output_artifact_refs", []) or []:
                artifact_type = ref.get("artifact_type")
                if artifact_type in wanted:
                    additions.append(ref)
                    wanted.remove(artifact_type)
            if not wanted:
                break
        return [*input_refs, *additions]

    async def _inject_reviewed_draft(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        input_refs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Bind revise to the exact draft named by its durable ReviewReport."""
        report_ref = next(
            (r for r in input_refs if r["artifact_type"] == "ReviewReport"), None
        )
        if report_ref is None:
            return input_refs
        report_artifact = await uow.artifacts.get(ArtifactId(report_ref["artifact_id"]))
        if report_artifact is None:
            return input_refs
        try:
            report = ReviewReport.model_validate(report_artifact.content)
        except Exception:  # noqa: BLE001 -- malformed artifact fails closed in the worker
            return input_refs
        artifacts = await uow.artifacts.list_for_episode(EpisodeId(run["episode_id"]))
        for artifact in artifacts:
            artifact_type = getattr(artifact.artifact_type, "value", str(artifact.artifact_type))
            if artifact_type != "ScreenplayDraft":
                continue
            try:
                draft = ScreenplayDraft.model_validate(artifact.content)
            except Exception:  # noqa: BLE001 -- skip unrelated malformed historical artifacts
                continue
            if draft.draft_id != report.draft_id:
                continue
            return [
                *input_refs,
                {
                    "artifact_id": str(artifact.artifact_id),
                    "artifact_type": "ScreenplayDraft",
                    "content_hash": artifact.content_hash,
                    "schema_version": artifact.schema_version,
                },
            ]
        return input_refs

    async def _inject_selected_idea(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        input_refs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Replay the selection command for bible.generate.

        User selection (revision metadata ``selected_candidate_id``, written
        by the public ``select_idea`` command) wins; otherwise the live
        scoring recommendation already carried by the evaluated candidate set
        (produced by the idea.evaluate node) is used. The SelectedIdea is
        persisted as a content-addressed artifact so the lock lineage can
        reference it, exactly like the B9 chain replay.
        """
        if any(r["artifact_type"] == "SelectedIdea" for r in input_refs):
            return input_refs
        set_ref = next(
            (r for r in input_refs if r["artifact_type"] == "IdeaCandidateSet"), None
        )
        if set_ref is None:
            return input_refs
        set_artifact = await uow.artifacts.get(ArtifactId(set_ref["artifact_id"]))
        if set_artifact is None:
            return input_refs
        try:
            candidate_set = IdeaCandidateSet.model_validate(set_artifact.content)
        except Exception:  # noqa: BLE001 — malformed upstream artifact fails closed at the worker
            return input_refs
        selected_id: Optional[str] = None
        run_rev = run["dag"].get("revision_id")
        if run_rev:
            revision = await uow.revisions.get(ProductionRevisionId(run_rev))
            if revision is not None:
                selected_id = (revision.metadata or {}).get("selected_candidate_id")
        source_set = candidate_set
        if selected_id is None:
            selected_id = candidate_set.recommended_candidate_id
        if not selected_id:
            return input_refs
        candidate = next(
            (c for c in source_set.candidates if c.candidate_id == selected_id), None
        )
        if candidate is None:
            return input_refs
        selected = SelectedIdea(
            selected_idea_id=SelectedIdeaId(
                f"sel_{run['run_id'][:12]}_{selected_id[:24]}"
            ),
            source_set_id=str(set_ref["artifact_id"]),
            candidate_id=selected_id,
            title=candidate.title,
            summary=candidate.summary,
            rationale=(
                "Orchestrator selection replay: user-selected candidate "
                "(select_idea) or live scoring recommendation."
            ),
            score=candidate.age_fit,
            selection_policy="AUTO_WHEN_POLICY_ALLOWS",
        )
        artifact = StoryArtifactEnvelope(
            artifact_id=ArtifactId(f"art_{selected.content_hash()[:16]}"),
            artifact_type="SelectedIdea",
            series_id=SeriesProjectId(run["series_id"]),
            episode_id=EpisodeId(run["episode_id"]),
            revision_id=(
                ProductionRevisionId(run_rev) if run_rev else None
            ),
            content_hash=selected.content_hash(),
            input_artifact_refs=[ArtifactId(str(set_ref["artifact_id"]))],
            created_by="orchestrator:auto-selection",
            content=selected.to_canonical_dict(),
        )
        await uow.artifacts.save(artifact)
        return [
            *input_refs,
            {
                "artifact_id": str(artifact.artifact_id),
                "artifact_type": "SelectedIdea",
                "content_hash": artifact.content_hash,
            },
        ]

    async def _lock_inputs(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        input_refs: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Complete the lock node's inputs and issue the A-issued receipt.

        The DAG edge into ``lock`` only carries the review node's outputs
        (ReviewReport); the frozen task IO map also needs the ScreenplayDraft,
        which the orchestrator completes from the screenplay.generate node's
        outputs. The receipt (A authority, B9 co-signed) binds that draft plus
        the approval mode/policy; the worker's lock handler validates it and
        assembles the immutable package from the live lineage hashes.
        """
        if not any(r["artifact_type"] == "ReviewReport" for r in input_refs):
            nodes = await uow.nodes.list(run["run_id"])
            initial_review = next(
                (n for n in nodes if n["dag_node_id"] == NODE_REVIEW), None
            )
            if initial_review is not None:
                input_refs = [
                    *input_refs,
                    *(
                        initial_review.get("output_artifact_refs", [])
                        or []
                    ),
                ]
        input_refs = await self._inject_reviewed_draft(uow, run, input_refs)
        draft_ref = next(
            (r for r in input_refs if r["artifact_type"] == "ScreenplayDraft"), None
        )
        if draft_ref is None:
            return input_refs, {}
        draft_artifact = await uow.artifacts.get(ArtifactId(draft_ref["artifact_id"]))
        if draft_artifact is None:
            return input_refs, {}
        try:
            draft = ScreenplayDraft.model_validate(draft_artifact.content)
        except Exception:  # noqa: BLE001 — malformed upstream artifact fails closed at the worker
            return input_refs, {}
        # Complete the lock lineage with every required package type. The DAG
        # edge only carries ReviewReport (+ the reviewed draft above); the
        # immutable package manifest needs the full 9-type lineage
        # (SelectedIdea lives in episode artifacts — it is A-side state, not
        # a DAG node output). Types already bound above are never replaced.
        missing_types = REQUIRED_PACKAGE_ARTIFACTS - {
            r["artifact_type"] for r in input_refs
        }
        if missing_types:
            episode_artifacts = await uow.artifacts.list_for_episode(
                EpisodeId(run["episode_id"])
            )
            for artifact in episode_artifacts:
                artifact_type = str(artifact.artifact_type.value)
                if artifact_type not in missing_types:
                    continue
                input_refs.append(
                    {
                        "artifact_type": artifact_type,
                        "artifact_id": str(artifact.artifact_id),
                        "content_hash": artifact.content_hash,
                        "revision_id": (
                            str(artifact.revision_id)
                            if artifact.revision_id is not None
                            else None
                        ),
                    }
                )
                missing_types.remove(artifact_type)
        policy = await self._load_policy(uow)
        mode = policy.mode_for(ApprovalCheckpoint.SCREENPLAY)
        receipt = LockedScreenplayReceipt(
            receipt_id=LockedScreenplayReceiptId(
                f"rcpt_{run['run_id'][:12]}_{draft.draft_id.value[:24]}"
            ),
            draft_id=draft.draft_id,
            approval_mode=mode.value,
            policy_id=policy.policy_id,
            issued_at=utc_now(),
        )
        return input_refs, {
            "receipt": receipt.to_canonical_dict(),
            "receipt_artifact_id": f"art_{receipt.receipt_id.value}",
            "lineage_refs": [
                ref
                for ref in input_refs
                if ref["artifact_type"] in REQUIRED_PACKAGE_ARTIFACTS
            ],
        }

    async def _submit_runnable_nodes(self, run_id: StudioRunId) -> None:
        """Durable dispatch: queue commit first, node identity second."""
        await submit_runnable_nodes(
            self._uow_factory, self._submission, run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )

    async def _advance_dependents(
        self, uow: StudioUnitOfWorkPort, run_id: StudioRunId, nodes: List[Dict[str, Any]]
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
        uow: StudioUnitOfWorkPort,
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
        uow: StudioUnitOfWorkPort,
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
        uow: StudioUnitOfWorkPort,
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
        uow_factory: StudioUnitOfWorkFactory,
        submission: StudioTaskSubmissionPort,
        *,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        policy_id: str = DEFAULT_APPROVAL_POLICY_ID,
    ) -> None:
        self._uow_factory = uow_factory
        self._submission = submission
        self._retry_budget = retry_budget
        self._policy_id = policy_id

    async def handle_task_result(self, result: StudioTaskResult) -> Dict[str, Any]:
        """Apply one durable task result; advance the DAG; submit new work.

        Returns a correlation dict; raises on stale/unknown completions.
        """
        async with self._uow_factory() as uow:
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
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        node: Dict[str, Any],
        result: StudioTaskResult,
    ) -> None:
        output_hashes = list(result.output_hashes)
        output_refs = [r.model_dump() for r in result.output_artifact_refs]
        if node["task_type"] in {
            StudioTaskType.SCREENPLAY_GENERATE.value,
            StudioTaskType.REVISE.value,
        }:
            await self._bind_screenplay_revision(uow, run, node, output_refs)
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
            checkpoint_episode: Optional[Episode] = None
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
                    checkpoint_episode = episode
                    auto_screenplay_review = (
                        node["task_type"] == StudioTaskType.REVIEW.value
                        and checkpoint == ApprovalCheckpoint.SCREENPLAY.value
                    )
                    if not auto_screenplay_review:
                        review_state = CHECKPOINT_TO_REVIEW_STATE[
                            ApprovalCheckpoint(checkpoint)
                        ]
                        if episode.state != review_state:
                            episode = StudioRunService._episode_transition(
                                episode, review_state
                            )
                            await uow.episodes.save(episode)
                        checkpoint_episode = episode
            if (
                node["task_type"] == StudioTaskType.REVIEW.value
                and checkpoint == ApprovalCheckpoint.SCREENPLAY.value
            ):
                report = await StudioRunService._review_report_for_gate(
                    uow, {"output_artifact_refs": output_refs}
                )
                await self._resolve_auto_review(
                    uow, run, node, report, episode=checkpoint_episode
                )
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

    async def _resolve_auto_review(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        node: Dict[str, Any],
        report: ReviewReport,
        *,
        episode: Optional[Episode],
    ) -> None:
        """Resolve an AUTO screenplay gate from its durable report."""
        if report.is_pass:
            if episode is None:
                episode = await uow.episodes.get(EpisodeId(run["episode_id"]))
            if episode is None:
                raise StudioNotFoundError(
                    "The reviewed screenplay episode no longer exists.",
                    details={"episode_id": str(run["episode_id"])},
                )
            if episode.state != EpisodeState.SCREENPLAY_REVIEW:
                episode = StudioRunService._episode_transition(
                    episode, EpisodeState.SCREENPLAY_REVIEW
                )
                await uow.episodes.save(episode)
            if node["dag_node_id"] == NODE_REVIEW:
                nodes = await uow.nodes.list(run["run_id"])
                for branch_node_id in (NODE_REVISE, NODE_REVIEW_REVISED):
                    branch = next(
                        n for n in nodes if n["dag_node_id"] == branch_node_id
                    )
                    if branch["status"] == StudioNodeStatus.PENDING.value:
                        await uow.nodes.update_node(
                            run["run_id"],
                            branch_node_id,
                            expected_version=branch["version"],
                            values={
                                "status": StudioNodeStatus.SKIPPED.value,
                                "error": "quality_revision_branch_not_required",
                            },
                        )
            return
        policy = await uow.approvals.get_policy(self._policy_id)
        if policy is None:
            policy = ApprovalPolicy(policy_id=self._policy_id, policy_version="1")
        StudioRunService._require_policy_revision_finding(policy, report)
        if episode is None:
            episode = await uow.episodes.get(EpisodeId(run["episode_id"]))
        if episode is None:
            raise StudioNotFoundError(
                "The reviewed screenplay episode no longer exists.",
                details={"episode_id": str(run["episode_id"])},
            )
        revising_state = (
            episode.state
            if episode.state == EpisodeState.REVISING
            else EpisodeStateMachine.transition(episode.state, EpisodeState.REVISING)
        )
        episode = StudioRunService._episode_update(
            episode,
            state=revising_state,
            awaiting_checkpoint=None,
        )
        await uow.episodes.save(episode)
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.STORY_REVISION_REQUESTED,
            run_id=run["run_id"],
            aggregate_id=str(run["episode_id"]),
            revision_ref=run["dag"].get("revision_id"),
            payload={
                "review_report_id": str(report.report_id),
                "draft_id": str(report.draft_id),
                "review_iteration": report.review_iteration,
                "finding_codes": [f.code for f in report.blocking_findings],
                "decision": "AUTO_POLICY",
            },
        )
        if node["dag_node_id"] == NODE_REVIEW_REVISED:
            await uow.runs.save(
                run["run_id"],
                series_id=run["series_id"],
                episode_id=run["episode_id"],
                dag=run["dag"],
                status="REVISION_REQUIRED",
                metadata={
                    **run.get("metadata", {}),
                    "revision_required": {
                        "review_report_id": str(report.report_id),
                        "review_iteration": report.review_iteration,
                        "reason": "AUTO_POLICY_THRESHOLD",
                    },
                },
            )
            run["status"] = "REVISION_REQUIRED"

    async def _bind_screenplay_revision(
        self,
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        node: Dict[str, Any],
        output_refs: List[Dict[str, Any]],
    ) -> None:
        """Make a persisted screenplay artifact the run's revision authority."""
        draft_ref = next(
            (r for r in output_refs if r["artifact_type"] == "ScreenplayDraft"),
            None,
        )
        if draft_ref is None:
            raise StudioValidationError(
                "A successful screenplay task must persist a ScreenplayDraft artifact.",
                details={"dag_node_id": node["dag_node_id"]},
            )
        draft_artifact = await uow.artifacts.get(ArtifactId(draft_ref["artifact_id"]))
        if draft_artifact is None:
            raise StudioValidationError(
                "The screenplay revision source is missing.",
                details={"artifact_id": str(draft_ref["artifact_id"])},
            )
        draft = ScreenplayDraft.model_validate(draft_artifact.content)
        if draft_artifact.content_hash != draft_ref["content_hash"]:
            raise StudioValidationError(
                "The screenplay artifact reference does not match persisted authority.",
                details={"artifact_id": str(draft_ref["artifact_id"])},
            )
        parent_id = run["dag"].get("revision_id")
        parent = (
            await uow.revisions.get(ProductionRevisionId(parent_id))
            if parent_id
            else None
        )
        if parent is None:
            raise StudioNotFoundError(
                "The run has no canonical parent revision for screenplay binding.",
                details={"run_id": str(run["run_id"]), "revision_id": parent_id},
            )
        revised = node["task_type"] == StudioTaskType.REVISE.value
        revision = StudioRevisionService.derive_revision(
            parent=parent,
            series_id=SeriesProjectId(run["series_id"]),
            episode_id=EpisodeId(run["episode_id"]),
            new_content_hash=draft_artifact.content_hash,
            creator="orchestrator:screenplay-artifact",
            actor="orchestrator:screenplay-artifact",
            invalidation_intent=(
                StudioInvalidationIntent.DOWNSTREAM if revised else None
            ),
            summary=(
                "Revision produced from blocking review findings."
                if revised
                else "Initial screenplay artifact bound to production revision."
            ),
        ).model_copy(
            update={
                "metadata": {
                    "source_screenplay_artifact_id": str(draft_artifact.artifact_id),
                    "source_screenplay_draft_id": str(draft.draft_id),
                    "source_dag_node_id": node["dag_node_id"],
                    "source_output_artifact_ids": [
                        str(ref["artifact_id"]) for ref in output_refs
                    ],
                }
            }
        )
        await uow.revisions.save(revision)
        episode = await uow.episodes.get(EpisodeId(run["episode_id"]))
        if episode is None:
            raise StudioNotFoundError(
                "The screenplay run episode no longer exists.",
                details={"episode_id": str(run["episode_id"])},
            )
        await uow.episodes.save(episode.attach_revision(revision.revision_id))
        dag = {**run["dag"], "revision_id": str(revision.revision_id)}
        metadata = {
            **run.get("metadata", {}),
            "revision_chain": [
                *(run.get("metadata", {}).get("revision_chain", [])),
                {
                    "revision_id": str(revision.revision_id),
                    "parent_revision_id": str(parent.revision_id),
                    "content_hash": revision.content_hash,
                    "source_artifact_id": str(draft_artifact.artifact_id),
                    "dag_node_id": node["dag_node_id"],
                },
            ],
        }
        await uow.runs.save(
            run["run_id"],
            series_id=run["series_id"],
            episode_id=run["episode_id"],
            dag=dag,
            status=run["status"],
            metadata=metadata,
        )
        run["dag"] = dag
        run["metadata"] = metadata
        await StudioRunService._emit(
            uow,
            StudioEventCatalog.REVISION_DERIVED,
            run_id=run["run_id"],
            aggregate_id=str(run["episode_id"]),
            revision_ref=str(revision.revision_id),
            payload={
                "parent_revision_id": str(parent.revision_id),
                "source_artifact_id": str(draft_artifact.artifact_id),
                "source_dag_node_id": node["dag_node_id"],
                "content_hash": revision.content_hash,
            },
        )

    async def _on_failed(
        self,
        uow: StudioUnitOfWorkPort,
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
        uow: StudioUnitOfWorkPort,
        run: Dict[str, Any],
        nodes: List[Dict[str, Any]],
    ) -> None:
        if run["status"] in RUN_TERMINAL_STATUSES:
            return
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
            self._uow_factory, self._submission, run_id,
            retry_budget=self._retry_budget, policy_id=self._policy_id,
        )


__all__ = ["StudioRunService", "StudioCompletionReconciler"]
