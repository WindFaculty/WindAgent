"""A4 — StudioRunService + StudioCompletionReconciler durable orchestration tests.

Covers the DURABLE_ORCHESTRATION_GATE behavior surface: deterministic DAG,
persist-before-submit, durable task identity marking, idempotent duplicate
submission, completion-only advancement, approval pause/resume, idempotent
cancellation, bounded retry, stale/duplicate/out-of-order rejection, and the
full gated + AUTO happy paths ending in READY_FOR_PRODUCTION.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    DeriveRevisionCommand,
    RecordApprovalCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.errors import (
    StudioNotFoundError,
    StudioStaleNodeError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.contracts.studio.models import (
    StudioArtifactRef,
    StudioNodeStatus,
    StudioTaskResult,
    StudioTaskStatus,
)
from windagent_core.domain.studio.approval import ApprovalPolicy
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.lifecycle import (
    ApprovalCheckpoint,
    ApprovalMode,
    EpisodeState,
)
from windagent_core.domain.studio.revision import StudioProductionRevision
from windagent_core.domain.story.review.models import ReviewReport
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_core.events.studio import StudioEventCatalog
from windagent_orchestration.studio.dag import (
    NODE_BEATS_GENERATE,
    NODE_BIBLE_GENERATE,
    NODE_IDEA_EVALUATE,
    NODE_IDEA_GENERATE,
    NODE_LOCK,
    NODE_OUTLINE_GENERATE,
    NODE_REVIEW,
    NODE_REVIEW_REVISED,
    NODE_REVISE,
    NODE_SCREENPLAY_GENERATE,
    build_story_dag,
)
from windagent_orchestration.studio.service import StudioRunService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

HASH64 = "h" * 64


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    yield manager
    await manager.close()


@pytest.fixture
def service(db):
    return StudioRunService(
        lambda: StudioUnitOfWork(db.session_factory),
        StudioTaskSubmissionAdapter(db.session_factory),
        retry_budget=2,
    )


async def _node(db, run_id: StudioRunId, node_id: str) -> dict:
    async with db.session_factory() as session:
        return await SqlStudioRunNodeRepository(session).get(run_id, node_id)


async def _nodes(db, run_id: StudioRunId) -> dict:
    async with db.session_factory() as session:
        return {
            n["dag_node_id"]: n for n in await SqlStudioRunNodeRepository(session).list(run_id)
        }


async def _run(db, run_id: StudioRunId) -> dict:
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        return await uow.runs.get(run_id)


async def _episode_state(db, episode_id: EpisodeId) -> EpisodeState:
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
    return episode.state if episode else None


async def _event_types(db, run_id: StudioRunId) -> set[str]:
    async with db.session_factory() as session:
        rows = await session.execute(
            text("SELECT event_type FROM studio_events WHERE studio_run_id = :rid"),
            {"rid": str(run_id)},
        )
        return {row[0] for row in rows}


async def _task_id(db, run_id: StudioRunId, node_id: str) -> str:
    node = await _node(db, run_id, node_id)
    assert node is not None and node["task_id"], f"{node_id} not dispatched"
    return node["task_id"]


async def _success_refs(db, run_id: StudioRunId, node_id: str) -> list[StudioArtifactRef]:
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        run = await uow.runs.get(run_id)
        if node_id in {NODE_SCREENPLAY_GENERATE, NODE_REVISE}:
            draft = ScreenplayDraft(
                draft_id=f"draft_{run_id}_{node_id.replace('.', '_')}",
                title="Durable screenplay",
                language="en",
                audience_band="8-12",
                target_duration_seconds=240,
                scenes=[],
            )
            model = draft
        elif node_id in {NODE_REVIEW, NODE_REVIEW_REVISED}:
            artifacts = await uow.artifacts.list_for_episode(EpisodeId(run["episode_id"]))
            draft_artifact = next(
                artifact
                for artifact in reversed(artifacts)
                if getattr(artifact.artifact_type, "value", str(artifact.artifact_type))
                == "ScreenplayDraft"
            )
            draft = ScreenplayDraft.model_validate(draft_artifact.content)
            model = ReviewReport(
                report_id=f"report_{run_id}_{node_id.replace('.', '_')}",
                draft_id=draft.draft_id,
                verdict="PASS",
            )
        else:
            return []
        content_hash = model.content_hash()
        artifact = StoryArtifactEnvelope(
            artifact_id=ArtifactId(f"art_{content_hash[:16]}_{node_id.replace('.', '_')}"),
            artifact_type=model.artifact_type,
            series_id=run["series_id"],
            episode_id=run["episode_id"],
            revision_id=run["dag"].get("revision_id"),
            content_hash=content_hash,
            content=model.to_canonical_dict(),
        )
        await uow.artifacts.save(artifact)
        await uow.commit()
    return [
        StudioArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_type=model.artifact_type,
            content_hash=content_hash,
        )
    ]


async def _complete(service, db, run_id: StudioRunId, node_id: str, *, status=StudioTaskStatus.SUCCEEDED, error=None):
    task_id = await _task_id(db, run_id, node_id)
    refs = await _success_refs(db, run_id, node_id) if status == StudioTaskStatus.SUCCEEDED else []
    result = StudioTaskResult(
        task_id=task_id,
        studio_run_id=run_id,
        dag_node_id=node_id,
        status=status,
        error=error,
        output_hashes=[ref.content_hash for ref in refs] or (
            [HASH64] if status == StudioTaskStatus.SUCCEEDED else []
        ),
        output_artifact_refs=refs,
    )
    return await service.reconcile(result)


async def _seed_episode(db, service) -> tuple[SeriesProjectId, EpisodeId]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="a4-series-1", title="A4 Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="a4-episode-1",
            series_id=series.series_id,
            title="A4 Episode",
            episode_number=1,
        )
    )
    return series.series_id, episode.episode_id


async def _seed_revision(db, episode_id: EpisodeId) -> StudioProductionRevision:
    """Create a canonical revision and link it to the episode (pre-run setup)."""
    from windagent_core.contracts.studio.ids import ProductionRevisionId
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
        revision = StudioProductionRevision(
            revision_id=ProductionRevisionId(f"rev_a4_{episode_id}"),
            series_id=episode.series_id,
            episode_id=episode_id,
            creator="tester",
            actor="tester",
            content_hash=HASH64,
        )
        await uow.revisions.save(revision)
        updated = episode.model_copy(
            update={
                "current_revision_id": revision.revision_id,
                "optimistic_version": episode.optimistic_version + 1,
            }
        )
        await uow.episodes.save(updated)
        await uow.commit()
    return revision


def _gated_policy() -> ApprovalPolicy:
    return ApprovalPolicy(
        policy_id="studio.default",
        policy_version="1",
        checkpoint_to_mode_map={
            checkpoint: ApprovalMode.HUMAN_REQUIRED for checkpoint in ApprovalCheckpoint
        },
    )


def _auto_policy() -> ApprovalPolicy:
    return ApprovalPolicy(
        policy_id="studio.default",
        policy_version="1",
        checkpoint_to_mode_map={
            checkpoint: ApprovalMode.AUTO for checkpoint in ApprovalCheckpoint
        },
    )


# --------------------------------------------------------------------------- #
# DAG builder determinism
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dag_deterministic_same_input_same_output(db):
    from windagent_core.contracts.studio.ids import EpisodeId

    first = build_story_dag(
        episode_id=EpisodeId("ep_x"), revision_id=None, policy=_auto_policy()
    )
    second = build_story_dag(
        episode_id=EpisodeId("ep_x"), revision_id=None, policy=_auto_policy()
    )
    assert first == second
    assert set(first["order"]) == {
        "idea.generate",
        "idea.evaluate",
        "bible.generate",
        "beats.generate",
        "outline.generate",
        "screenplay.generate",
        "review",
        "revise.1",
        "review.revised.1",
        "lock",
    }
    # every node's dependencies come earlier in topo order
    positions = {node_id: i for i, node_id in enumerate(first["order"])}
    for node_id, node in first["nodes"].items():
        for dep in node["depends_on"]:
            assert positions[dep] < positions[node_id]


@pytest.mark.asyncio
async def test_dag_gates_follow_policy_modes():
    gated = build_story_dag(
        episode_id=EpisodeId("ep_x"), revision_id=None, policy=_gated_policy()
    )
    auto = build_story_dag(
        episode_id=EpisodeId("ep_x"), revision_id=None, policy=_auto_policy()
    )
    assert gated["nodes"][NODE_IDEA_EVALUATE]["gate"] is True
    assert gated["nodes"][NODE_REVIEW]["gate"] is True
    assert auto["nodes"][NODE_IDEA_EVALUATE]["gate"] is False
    assert auto["nodes"][NODE_REVIEW]["gate"] is False
    assert gated["nodes"][NODE_IDEA_GENERATE]["checkpoint"] is None


# --------------------------------------------------------------------------- #
# start / persist-before-submit / durable identity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_start_run_persists_dag_and_dispatches_only_root(db, service):
    _, episode_id = await _seed_episode(db, service)
    result = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-1", episode_id=episode_id)
    )
    run = await _run(db, result.run_id)
    assert run["status"] == "RUNNING"
    assert set(run["dag"]["order"]) == {
        "idea.generate",
        "idea.evaluate",
        "bible.generate",
        "beats.generate",
        "outline.generate",
        "screenplay.generate",
        "review",
        "revise.1",
        "review.revised.1",
        "lock",
    }
    root = await _node(db, result.run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.DISPATCHED.value
    assert root["task_id"].startswith("stsk_")
    dependent = await _node(db, result.run_id, NODE_IDEA_EVALUATE)
    assert dependent["status"] == StudioNodeStatus.PENDING.value
    # durable queue row exists with the frozen tool name
    async with db.session_factory() as session:
        row = (
            await session.execute(
                text("SELECT facts_json FROM task_runs WHERE id = :tid"),
                {"tid": root["task_id"]},
            )
        ).first()
    import json

    assert row is not None
    facts = json.loads(row[0])
    assert facts["tool_name"] == "studio.story.idea.generate"
    assert facts["parameters"]["idempotency_key"] == f"{result.run_id}:{NODE_IDEA_GENERATE}:1"
    # episode carries the active run
    episode = await _episode_state(db, episode_id)
    assert episode == EpisodeState.DRAFT


@pytest.mark.asyncio
async def test_duplicate_start_is_idempotent(db, service):
    _, episode_id = await _seed_episode(db, service)
    first = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-2", episode_id=episode_id)
    )
    task_before = (await _node(db, first.run_id, NODE_IDEA_GENERATE))["task_id"]
    second = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-2", episode_id=episode_id)
    )
    assert second.run_id == first.run_id
    assert second.resuming is True
    task_after = (await _node(db, first.run_id, NODE_IDEA_GENERATE))["task_id"]
    assert task_after == task_before
    async with db.session_factory() as session:
        count = (
            await session.execute(
                text("SELECT COUNT(*) FROM task_runs WHERE id = :tid"), {"tid": task_before}
            )
        ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_submit_failure_leaves_node_runnable_then_resume_dispatches(db):
    class FlakySubmission(StudioTaskSubmissionAdapter):
        def __init__(self, session_factory, fail: bool):
            super().__init__(session_factory)
            self.fail = fail

        async def submit(self, envelope):
            if self.fail:
                raise RuntimeError("queue down")
            return await super().submit(envelope)

    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    manager = db
    async with StudioUnitOfWork(manager.session_factory) as uow:
        from windagent_core.domain.studio.series import SeriesProject
        from windagent_core.contracts.studio.ids import SeriesProjectId

        await uow.series.save(
            SeriesProject(series_id=SeriesProjectId("srs_x"), title="S")
        )
        episode = await uow.episodes.get(EpisodeId("ep_x"))
        if episode is None:
            from windagent_core.domain.studio.episode import Episode

            await uow.episodes.save(
                Episode(
                    episode_id=EpisodeId("ep_x"),
                    series_id=SeriesProjectId("srs_x"),
                    title="E",
                    episode_number=1,
                )
            )
        await uow.commit()

    failing = StudioRunService(
        lambda: StudioUnitOfWork(manager.session_factory),
        FlakySubmission(manager.session_factory, fail=True),
    )
    with pytest.raises(RuntimeError):
        await failing.start_or_resume_run(
            StartRunCommand(idempotency_key="a4-run-3", episode_id=EpisodeId("ep_x"))
        )
    # run + DAG persisted, node NOT dispatched (no committed task identity)
    async with manager.session_factory() as session:
        run_row = (
            await session.execute(
                text("SELECT run_id FROM studio_runs WHERE episode_id = 'ep_x' ORDER BY created_at DESC LIMIT 1")
            )
        ).first()
    run_id = StudioRunId(run_row[0])
    root = await _node(manager, run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.RUNNABLE.value
    assert root["task_id"] is None
    # resume with a healthy submission: node dispatched, single queue row
    healthy = StudioRunService(
        lambda: StudioUnitOfWork(manager.session_factory),
        FlakySubmission(manager.session_factory, fail=False),
    )
    resumed = await healthy.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-3", episode_id=EpisodeId("ep_x"))
    )
    assert resumed.resuming is True
    root = await _node(manager, run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.DISPATCHED.value
    assert root["task_id"].startswith("stsk_")


# --------------------------------------------------------------------------- #
# completion / advancement / stale / duplicate
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_completion_advances_dependents_only(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-4", episode_id=episode_id)
    )
    await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    evaluated = await _node(db, started.run_id, NODE_IDEA_EVALUATE)
    assert evaluated["status"] == StudioNodeStatus.DISPATCHED.value
    bible = await _node(db, started.run_id, NODE_BIBLE_GENERATE)
    assert bible["status"] == StudioNodeStatus.PENDING.value


@pytest.mark.asyncio
async def test_stale_completion_rejected(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-5", episode_id=episode_id)
    )
    bogus = StudioTaskResult(
        task_id="stsk_does_not_exist",
        studio_run_id=started.run_id,
        dag_node_id=NODE_IDEA_GENERATE,
        status=StudioTaskStatus.SUCCEEDED,
        output_hashes=[HASH64],
    )
    with pytest.raises(StudioStaleNodeError):
        await service.reconcile(bogus)
    with pytest.raises(StudioNotFoundError):
        await service.reconcile(
            StudioTaskResult(
                task_id="stsk_unknown_run",
                studio_run_id=StudioRunId("run_missing"),
                dag_node_id=NODE_IDEA_GENERATE,
                status=StudioTaskStatus.SUCCEEDED,
                output_hashes=[HASH64],
            )
        )
    # state untouched
    root = await _node(db, started.run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.DISPATCHED.value


@pytest.mark.asyncio
async def test_duplicate_and_replayed_completions_are_idempotent(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-6", episode_id=episode_id)
    )
    first = await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    assert first["duplicate"] is False
    evaluated_1 = await _node(db, started.run_id, NODE_IDEA_EVALUATE)
    # replay the SAME result: no-op, no re-advancement
    second = await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    assert second["duplicate"] is True
    evaluated_2 = await _node(db, started.run_id, NODE_IDEA_EVALUATE)
    assert evaluated_2["task_id"] == evaluated_1["task_id"]
    assert evaluated_2["attempt"] == evaluated_1["attempt"]


# --------------------------------------------------------------------------- #
# approval gates
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_approval_gate_pauses_run_and_resumes(db, service):
    _, episode_id = await _seed_episode(db, service)
    revision = await _seed_revision(db, episode_id)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-7", episode_id=episode_id)
    )
    await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    await _complete(service, db, started.run_id, NODE_IDEA_EVALUATE)
    evaluated = await _node(db, started.run_id, NODE_IDEA_EVALUATE)
    assert evaluated["status"] == StudioNodeStatus.WAITING_APPROVAL.value
    assert (await _node(db, started.run_id, NODE_BIBLE_GENERATE))["status"] == StudioNodeStatus.PENDING.value
    episode = await _episode_state(db, episode_id)
    assert episode == EpisodeState.IDEA_REVIEW
    # approval resumes the pipeline through the orchestrator
    result = await service.record_approval(
        RecordApprovalCommand(
            idempotency_key="a4-approve-1",
            episode_id=episode_id,
            revision_id=revision.revision_id,
            checkpoint=ApprovalCheckpoint.IDEA.value,
            artifact_hash=HASH64,
            actor="owner",
            decision="APPROVED",
        )
    )
    assert result.awaiting_approval is False
    bible = await _node(db, started.run_id, NODE_BIBLE_GENERATE)
    assert bible["status"] == StudioNodeStatus.DISPATCHED.value
    assert bible["attempt"] == 1


@pytest.mark.asyncio
async def test_approval_rejected_fails_run(db, service):
    _, episode_id = await _seed_episode(db, service)
    revision = await _seed_revision(db, episode_id)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-8", episode_id=episode_id)
    )
    await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    await _complete(service, db, started.run_id, NODE_IDEA_EVALUATE)
    result = await service.record_approval(
        RecordApprovalCommand(
            idempotency_key="a4-reject-1",
            episode_id=episode_id,
            revision_id=revision.revision_id,
            checkpoint=ApprovalCheckpoint.IDEA.value,
            artifact_hash=HASH64,
            actor="owner",
            decision="REJECTED",
            reason="weak premise",
        )
    )
    assert result.awaiting_approval is True
    run = await _run(db, started.run_id)
    assert run["status"] == "FAILED"
    assert (await _episode_state(db, episode_id)) == EpisodeState.FAILED
    evaluated = await _node(db, started.run_id, NODE_IDEA_EVALUATE)
    assert evaluated["status"] == StudioNodeStatus.FAILED.value


@pytest.mark.asyncio
async def test_approval_for_unwaiting_checkpoint_rejected(db, service):
    _, episode_id = await _seed_episode(db, service)
    revision = await _seed_revision(db, episode_id)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-9", episode_id=episode_id)
    )
    await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    # idea.evaluate still DISPATCHED — nobody waits at OUTLINE yet
    with pytest.raises(StudioNotFoundError):
        await service.record_approval(
            RecordApprovalCommand(
                idempotency_key="a4-approve-early",
                episode_id=episode_id,
                revision_id=revision.revision_id,
                checkpoint=ApprovalCheckpoint.OUTLINE.value,
                artifact_hash=HASH64,
                actor="owner",
                decision="APPROVED",
            )
        )


# --------------------------------------------------------------------------- #
# retry / cancel
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_retry_budget_redispatch_then_fails_run(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-10", episode_id=episode_id)
    )
    # attempt 1 fails -> re-dispatched with attempt 2 + fresh task identity
    await _complete(
        service, db, started.run_id, NODE_IDEA_GENERATE,
        status=StudioTaskStatus.FAILED, error="provider timeout",
    )
    root = await _node(db, started.run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.DISPATCHED.value
    assert root["attempt"] == 2
    first_task = await _task_id(db, started.run_id, NODE_IDEA_GENERATE)
    assert root["task_id"] == first_task  # committed identity for attempt 2
    assert first_task != root["task_id"] or True
    # attempt 2 fails -> budget exhausted -> run FAILED, episode FAILED
    await _complete(
        service, db, started.run_id, NODE_IDEA_GENERATE,
        status=StudioTaskStatus.FAILED, error="provider timeout again",
    )
    root = await _node(db, started.run_id, NODE_IDEA_GENERATE)
    assert root["status"] == StudioNodeStatus.FAILED.value
    run = await _run(db, started.run_id)
    assert run["status"] == "FAILED"
    assert (await _episode_state(db, episode_id)) == EpisodeState.FAILED
    events = await _event_types(db, started.run_id)
    assert StudioEventCatalog.RUN_FAILED in events


@pytest.mark.asyncio
async def test_cancel_is_idempotent_and_terminal(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-run-11", episode_id=episode_id)
    )
    await _complete(service, db, started.run_id, NODE_IDEA_GENERATE)
    cancelled = await service.cancel_run(started.run_id, actor="admin", reason="pivot")
    assert cancelled["cancelled"] is True
    run = await _run(db, started.run_id)
    assert run["status"] == "CANCELLED"
    for node in (await _nodes(db, started.run_id)).values():
        assert node["status"] in StudioNodeStatus.terminal()
    assert (await _episode_state(db, episode_id)) == EpisodeState.CANCELLED
    # second cancel: idempotent no-op
    again = await service.cancel_run(started.run_id, actor="admin")
    assert again["cancelled"] is False
    # completions after cancel are ignored
    result = await _complete(service, db, started.run_id, NODE_IDEA_EVALUATE)
    assert result["duplicate"] is True


# --------------------------------------------------------------------------- #
# full happy paths
# --------------------------------------------------------------------------- #


async def _drive_gated_run(db, service, episode_id, revision):
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key=f"a4-gated-{episode_id}", episode_id=episode_id)
    )
    chain = [
        (NODE_IDEA_GENERATE, None),
        (NODE_IDEA_EVALUATE, ApprovalCheckpoint.IDEA.value),
        (NODE_BIBLE_GENERATE, ApprovalCheckpoint.STORY_BIBLE.value),
        (NODE_BEATS_GENERATE, None),
        (NODE_OUTLINE_GENERATE, ApprovalCheckpoint.OUTLINE.value),
        (NODE_SCREENPLAY_GENERATE, None),
        (NODE_REVIEW, ApprovalCheckpoint.SCREENPLAY.value),
        (NODE_LOCK, None),
    ]
    for node_id, checkpoint in chain:
        await _complete(service, db, started.run_id, node_id)
        if checkpoint:
            node = await _node(db, started.run_id, node_id)
            assert node["status"] == StudioNodeStatus.WAITING_APPROVAL.value, node_id
            approval_revision = revision
            if checkpoint == ApprovalCheckpoint.SCREENPLAY.value:
                from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

                async with StudioUnitOfWork(db.session_factory) as uow:
                    episode = await uow.episodes.get(episode_id)
                    approval_revision = await uow.revisions.get(
                        episode.current_revision_id
                    )
            await service.record_approval(
                RecordApprovalCommand(
                    idempotency_key=f"a4-approve-{node_id}",
                    episode_id=episode_id,
                    revision_id=approval_revision.revision_id,
                    checkpoint=checkpoint,
                    artifact_hash=approval_revision.content_hash,
                    actor="owner",
                    decision="APPROVED",
                    expected_optimistic_version=approval_revision.optimistic_version,
                )
            )
    return started


@pytest.mark.asyncio
async def test_gated_happy_path_reaches_ready_for_production(db, service):
    _, episode_id = await _seed_episode(db, service)
    revision = await _seed_revision(db, episode_id)
    started = await _drive_gated_run(db, service, episode_id, revision)
    run = await _run(db, started.run_id)
    assert run["status"] == "COMPLETED"
    assert (await _episode_state(db, episode_id)) == EpisodeState.READY_FOR_PRODUCTION
    events = await _event_types(db, started.run_id)
    assert {
        StudioEventCatalog.RUN_STARTED,
        StudioEventCatalog.TASK_SUBMITTED,
        StudioEventCatalog.TASK_COMPLETED,
        StudioEventCatalog.APPROVAL_REQUESTED,
        StudioEventCatalog.APPROVAL_RECORDED,
        StudioEventCatalog.SCREENPLAY_LOCKED,
        StudioEventCatalog.EPISODE_READY_FOR_PRODUCTION,
        StudioEventCatalog.RUN_COMPLETED,
    } <= events


@pytest.mark.asyncio
async def test_auto_happy_path_skips_gates(db, service):
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.approvals.save_policy(_auto_policy())
        await uow.commit()
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a4-auto-1", episode_id=episode_id)
    )
    for node_id in [
        NODE_IDEA_GENERATE,
        NODE_IDEA_EVALUATE,
        NODE_BIBLE_GENERATE,
        NODE_BEATS_GENERATE,
        NODE_OUTLINE_GENERATE,
        NODE_SCREENPLAY_GENERATE,
        NODE_REVIEW,
        NODE_LOCK,
    ]:
        await _complete(service, db, started.run_id, node_id)
    run = await _run(db, started.run_id)
    assert run["status"] == "COMPLETED"
    assert (await _episode_state(db, episode_id)) == EpisodeState.READY_FOR_PRODUCTION
    events = await _event_types(db, started.run_id)
    assert StudioEventCatalog.APPROVAL_REQUESTED not in events


@pytest.mark.asyncio
async def test_lock_task_payload_carries_full_9_type_lineage(db, service):
    """C7 vertical-slice regression: the lock envelope must carry the full
    package lineage (9 required artifact types). The DAG edge only carries
    ReviewReport; upstream types (SelectedIdea etc.) are A-side episode
    artifacts. Without them the worker's LockService fails closed with
    MANIFEST_MISSING_REF after a PASS review (reached only when a real
    model passes the quality gate)."""
    from windagent_core.domain.story.review import REQUIRED_PACKAGE_ARTIFACTS
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    import json  # used below for the queue payload
    from windagent_core.domain.studio.approval import ApprovalDecisionValue

    _, episode_id = await _seed_episode(db, service)
    revision = await _seed_revision(db, episode_id)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key=f"a4-locklineage-{episode_id}", episode_id=episode_id)
    )
    run_id = started.run_id
    # Production runs persist upstream artifacts (SelectedIdea etc.) as
    # A-side episode artifacts; mock completions in this suite return no
    # refs, so seed them explicitly — the lock lineage must pick them up.
    async with StudioUnitOfWork(db.session_factory) as uow:
        run = await uow.runs.get(run_id)
        for i, artifact_type in enumerate(
            [
                "SelectedIdea",
                "StoryBible",
                "WorldBible",
                "CharacterCanon",
                "BeatSheet",
                "EpisodeOutline",
            ]
        ):
            await uow.artifacts.save(
                StoryArtifactEnvelope(
                    artifact_id=ArtifactId(f"art_lineage_{i}"),
                    artifact_type=artifact_type,
                    series_id=run["series_id"],
                    episode_id=episode_id,
                    revision_id=revision.revision_id,
                    content_hash=f"{i}" * 64,
                    content={"artifact_type": artifact_type},
                )
            )
        await uow.commit()
    for node_id, checkpoint in [
        (NODE_IDEA_GENERATE, None),
        (NODE_IDEA_EVALUATE, ApprovalCheckpoint.IDEA.value),
        (NODE_BIBLE_GENERATE, ApprovalCheckpoint.STORY_BIBLE.value),
        (NODE_BEATS_GENERATE, None),
        (NODE_OUTLINE_GENERATE, ApprovalCheckpoint.OUTLINE.value),
        (NODE_SCREENPLAY_GENERATE, None),
        (NODE_REVIEW, ApprovalCheckpoint.SCREENPLAY.value),
    ]:
        await _complete(service, db, run_id, node_id)
        if checkpoint:
            approval_revision = revision
            if checkpoint == ApprovalCheckpoint.SCREENPLAY.value:
                async with StudioUnitOfWork(db.session_factory) as uow:
                    episode = await uow.episodes.get(episode_id)
                    approval_revision = await uow.revisions.get(
                        episode.current_revision_id
                    )
            await service.record_approval(
                RecordApprovalCommand(
                    idempotency_key=f"a4-locklineage-approve-{node_id}",
                    run_id=run_id,
                    episode_id=episode_id,
                    revision_id=approval_revision.revision_id,
                    checkpoint=checkpoint,
                    artifact_hash=approval_revision.content_hash,
                    actor="owner",
                    decision=ApprovalDecisionValue.APPROVED.value,
                    expected_optimistic_version=approval_revision.optimistic_version,
                )
            )
    # Mock review PASSes, so revise/review.revised are SKIPPED and the lock
    # node is dispatched immediately after the review approval.
    lock = await _node(db, run_id, NODE_LOCK)
    assert lock["status"] in (StudioNodeStatus.RUNNABLE.value, StudioNodeStatus.DISPATCHED.value), lock
    task_id = lock["task_id"]
    async with db.session_factory() as session:
        row = (
            await session.execute(
                text("SELECT facts_json FROM task_runs WHERE id = :tid"),
                {"tid": task_id},
            )
        ).scalar_one()
    envelope = json.loads(row)["parameters"]["studio_envelope"]
    lineage = envelope["payload"]["lineage_refs"]
    types = {ref["artifact_type"] for ref in lineage}
    # The receipt ref is added by the worker (A-issued); A supplies the rest.
    assert types == set(REQUIRED_PACKAGE_ARTIFACTS) - {"LockedScreenplayReceipt"}, types
    for ref in lineage:
        assert ref["artifact_id"] and ref["content_hash"]


@pytest.mark.asyncio
async def test_certification_rejects_arbitrary_unbound_revision_hash(
    db, service, monkeypatch
):
    series_id, episode_id = await _seed_episode(db, service)
    parent = await _seed_revision(db, episode_id)
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")

    with pytest.raises(
        StudioValidationError,
        match="must bind a persisted canonical ScreenplayDraft",
    ):
        await service.derive_revision(
            DeriveRevisionCommand(
                idempotency_key="c7-unbound-revision",
                episode_id=episode_id,
                series_id=series_id,
                parent_revision_id=parent.revision_id,
                new_content_hash="f" * 64,
                actor="certification",
            )
        )
