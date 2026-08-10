"""A5 — Studio worker runtime tests (STORY_WORKER_GATE surface).

Covers envelope validation before side effects, unregistered/fake/fixture
rejection (certification profile), B handler execution through the worker
seam (real SQL queue, independent worker, Studio UoW, generic finalizer,
completion reconciler), artifact idempotency, cancellation, stale fencing,
duplicate delivery, restart recovery, and redaction-safe worker metrics.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import ExecutionRequest
from windagent_core.contracts.finalization import FinalizeTaskExecutionRequest, StaleResultRejectedError
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, SeriesProjectId, StudioRunId
from windagent_core.contracts.studio.models import (
    StudioArtifactRef,
    StudioTaskEnvelope,
    StudioTaskResult,
    StudioTaskStatus,
    StudioTaskType,
)
from windagent_core.domain.story.ideation.models import CreativeBrief, IdeaCandidate, IdeaCandidateSet
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_intelligence.story.prompts.fixture import FixtureModelPort
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
from windagent_orchestration.studio.service import StudioRunService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_worker.runner import ProductionWorker
from windagent_worker.studio_runtime import (
    CERTIFICATION_VIOLATION,
    ENVELOPE_INVALID,
    UNREGISTERED_TASK_TYPE,
    StudioCompletionRecovery,
    StudioRuntimeAdapter,
)

import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401

HASH64 = "a" * 64

BRIEF_DICT = {
    "brief_id": "brf_a5_1",
    "title": "A5 Episode",
    "genre": "fantasy",
    "logline": "A rabbit and a kite cross the valley.",
    "tone": "warm",
    "audience": "kids",
    "language": "vi",
    "theme": "friendship",
    "target_duration_seconds": 240,
    "aspect_ratio": "16:9",
}

FIXTURE_RESPONSE = {
    "language": "vi",
    "candidates": [
        {
            "candidate_id": f"c{i}",
            "title": f"Title {i}",
            "summary": "s",
            "premise": "p",
            "logline": "l",
            "themes": [],
            "age_fit": 0.9,
            "estimated_seconds": 240,
            "scene_count": 5,
            "character_count": 2,
            "location_count": 2,
            "safety_ok": True,
        }
        for i in range(1, 4)
    ],
}


def _candidates() -> list[IdeaCandidate]:
    return [IdeaCandidate(**c) for c in FIXTURE_RESPONSE["candidates"]]


async def _seed_episode(db, service, *, brief: dict | None = None) -> tuple[SeriesProjectId, EpisodeId]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="a5-series-1", title="A5 Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="a5-episode-1",
            series_id=series.series_id,
            title="A5 Episode",
            episode_number=1,
            metadata={"creative_brief": brief} if brief else {},
        )
    )
    return series.series_id, episode.episode_id


async def _save_artifact(db, envelope: StoryArtifactEnvelope) -> StoryArtifactEnvelope:
    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.artifacts.save(envelope)
        await uow.commit()
    return envelope


async def _seed_candidate_set(db, series_id: SeriesProjectId, episode_id: EpisodeId) -> StoryArtifactEnvelope:
    model = IdeaCandidateSet(candidates=_candidates())
    artifact = StoryArtifactEnvelope(
        artifact_id=ArtifactId("art_a5_candidates"),
        artifact_type=model.artifact_type,
        series_id=series_id,
        episode_id=episode_id,
        content_hash=model.content_hash(),
        content=model.to_canonical_dict(),
    )
    return await _save_artifact(db, artifact)


def _envelope(
    task_type: StudioTaskType,
    *,
    episode_id: EpisodeId,
    series_id: SeriesProjectId,
    run_id: StudioRunId | None = None,
    input_refs: list[StudioArtifactRef] | None = None,
    schema_version: str | None = None,
    contract_version: str | None = None,
) -> StudioTaskEnvelope:
    return StudioTaskEnvelope(
        task_type=task_type,
        studio_run_id=run_id or StudioRunId("run_a5_1"),
        dag_node_id="idea.generate",
        series_id=series_id,
        episode_id=episode_id,
        input_artifact_refs=input_refs or [],
        idempotency_key="a5-key-1",
        schema_version=schema_version or "studio.task_envelope/v1",
        contract_version=contract_version or "studio.contract/v0.1",
    )


async def _adapter(db, **kwargs) -> StudioRuntimeAdapter:
    return StudioRuntimeAdapter(
        handler_registry=HANDLER_REGISTRY,
        session_factory=db.session_factory,
        **kwargs,
    )


async def _dispatch(adapter: StudioRuntimeAdapter, envelope: StudioTaskEnvelope, task_id: str) -> dict:
    request = ExecutionRequest(
        step_run_id=task_id,
        workflow_run_id=f"wf_{task_id}",
        tool_name=envelope.task_type.value,
        parameters={"studio_envelope": envelope.to_dict()},
        attempt_id="att_1",
        fencing_token=f"fence_{task_id}_gen_1_abc123",
    )
    handle = await adapter.dispatch(request)
    return await adapter.get_result(handle)


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    yield manager
    await manager.close()


@pytest.fixture
def service(db):
    return StudioRunService(
        db.session_factory,
        StudioTaskSubmissionAdapter(db.session_factory),
        retry_budget=2,
    )


@pytest.fixture
def studio(db):
    """Throwaway StudioRunService used only to seed series/episodes."""
    return StudioRunService(
        db.session_factory,
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


async def _artifact_count(db) -> int:
    async with db.session_factory() as session:
        row = await session.execute(text("SELECT COUNT(*) FROM studio_artifacts"))
        return row.scalar_one()


# ---------------------------------------------------------------------------
# Envelope validation before side effects
# ---------------------------------------------------------------------------


async def test_envelope_missing_rejected_without_side_effects(db):
    adapter = await _adapter(db)
    request = ExecutionRequest(
        step_run_id="t1",
        workflow_run_id="wf_t1",
        tool_name="studio.story.idea.generate",
        parameters={},
        attempt_id="att_1",
        fencing_token="fence_t1",
    )
    handle = await adapter.dispatch(request)
    result = await adapter.get_result(handle)
    assert result.status.value == "failed"
    assert result.error.startswith(ENVELOPE_INVALID)
    assert await _artifact_count(db) == 0


async def test_unsupported_envelope_schema_rejected(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(db)
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        schema_version="studio.task_envelope/v999",
    )
    result = await _dispatch(adapter, envelope, "t2")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith(ENVELOPE_INVALID)
    assert await _artifact_count(db) == 0


async def test_unsupported_contract_rejected(db, studio):
    series_id, episode_id = await _seed_episode(db, studio)
    adapter = await _adapter(db)
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        contract_version="studio.contract/v0.2",
    )
    result = await _dispatch(adapter, envelope, "t3")
    data = result.result_data or {}
    assert data.get("error").startswith(ENVELOPE_INVALID)


async def test_unregistered_task_type_rejected(db, studio):
    series_id, episode_id = await _seed_episode(db, studio)
    adapter = await _adapter(db)
    envelope = _envelope(
        StudioTaskType.LOCK,  # frozen type, handler lands in a later B phase
        episode_id=episode_id,
        series_id=series_id,
    )
    result = await _dispatch(adapter, envelope, "t4")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith(UNREGISTERED_TASK_TYPE)
    assert await _artifact_count(db) == 0


# ---------------------------------------------------------------------------
# Certification profile: fake runtime / fixture providers fail closed
# ---------------------------------------------------------------------------


async def test_fake_runtime_rejected_in_certification(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
        certification=True,
        fake_runtime_active=True,
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    result = await _dispatch(adapter, envelope, "t5")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith(CERTIFICATION_VIOLATION)
    assert await _artifact_count(db) == 0


async def test_fixture_provider_rejected_in_certification(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
        certification=True,
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    result = await _dispatch(adapter, envelope, "t6")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith(CERTIFICATION_VIOLATION)
    assert await _artifact_count(db) == 0


# ---------------------------------------------------------------------------
# Handler execution + artifact persistence (non-certification stub allowed)
# ---------------------------------------------------------------------------


async def test_idea_generate_persists_artifacts_with_fixture_stub(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    result = await _dispatch(adapter, envelope, "t7")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.SUCCEEDED.value
    assert len(data["output_artifact_refs"]) == 1
    ref = data["output_artifact_refs"][0]
    assert ref["artifact_type"] == "IdeaCandidateSet"
    assert len(ref["content_hash"]) == 64
    assert await _artifact_count(db) == 1
    async with StudioUnitOfWork(db.session_factory) as uow:
        stored = await uow.artifacts.get(ArtifactId(ref["artifact_id"]))
    assert stored is not None
    assert stored.content_hash == ref["content_hash"]
    assert stored.created_by.startswith("worker:studio-worker:task:t7")


async def test_idea_evaluate_pure_handler_roundtrip(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    seeded = await _seed_candidate_set(db, series_id, episode_id)
    adapter = await _adapter(db)  # evaluate needs no model port
    envelope = _envelope(
        StudioTaskType.IDEA_EVALUATE,
        episode_id=episode_id,
        series_id=series_id,
        input_refs=[
            StudioArtifactRef(
                artifact_id=seeded.artifact_id,
                artifact_type="IdeaCandidateSet",
                content_hash=seeded.content_hash,
            )
        ],
    )
    result = await _dispatch(adapter, envelope, "t8")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.SUCCEEDED.value
    assert len(data["output_artifact_refs"]) == 1
    assert await _artifact_count(db) == 2  # seeded + evaluated set


async def test_artifact_write_idempotent_by_hash(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    first = await _dispatch(adapter, envelope, "t9a")
    second = await _dispatch(adapter, envelope, "t9b")  # same content, new task
    assert first.result_data["output_artifact_refs"] == second.result_data["output_artifact_refs"]
    assert await _artifact_count(db) == 1  # content-addressed reuse


async def test_missing_input_artifact_fails_closed(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(db)
    envelope = _envelope(
        StudioTaskType.IDEA_EVALUATE, episode_id=episode_id, series_id=series_id
    )  # no refs at all
    result = await _dispatch(adapter, envelope, "t10")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith("STUDIO_INPUT_ARTIFACT_MISSING")
    assert await _artifact_count(db) == 0


async def test_cancel_check_aborts_before_side_effects(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
        cancel_check=lambda: True,
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    result = await _dispatch(adapter, envelope, "t11")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.CANCELLED.value
    assert await _artifact_count(db) == 0


async def test_model_port_required_handler_fails_closed_without_port(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(db, model_port=None)
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE, episode_id=episode_id, series_id=series_id
    )
    result = await _dispatch(adapter, envelope, "t12")
    data = result.result_data or {}
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert result.error.startswith("STUDIO_MODEL_PORT_UNAVAILABLE")


async def test_registry_routes_studio_capability(db, studio):
    registry = ExecutionRuntimeRegistry()
    adapter = await _adapter(db)
    registry.register_capability("studio", adapter)
    assert registry.resolve_adapter("studio.story.idea.generate") is adapter
    assert registry.resolve_adapter("read_file") is not adapter


# ---------------------------------------------------------------------------
# E2E: real SQL queue -> independent worker -> UoW -> finalizer -> reconciler
# ---------------------------------------------------------------------------


async def _make_worker(db, *, studio_reconciler=None, studio_recovery=None, **runtime_kwargs):
    adapter = await _adapter(db, **runtime_kwargs)
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("studio", adapter)
    worker = ProductionWorker(
        name="a5-test-worker",
        task_queue=SqlDurableTaskQueue(db.session_factory),
        execution_registry=registry,
        uow_factory=db.session_factory,
        studio_reconciler=studio_reconciler,
        studio_recovery=studio_recovery,
    )
    return worker


async def _start_run_with_brief(db, service, brief: dict | None = None) -> tuple[SeriesProjectId, EpisodeId, StudioRunId]:
    series_id, episode_id = await _seed_episode(db, service, brief=brief)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="a5-run-1", episode_id=episode_id)
    )
    return series_id, episode_id, started.run_id


async def test_b_handler_crosses_worker_queue_finalizer_reconciler(db, service):
    """Gate path: idea.generate crosses the whole durable chain; the DAG
    advances ONLY through the reconciler (idea.evaluate gets dispatched)."""
    _, episode_id, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)
    worker = await _make_worker(
        db,
        studio_reconciler=service,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    await worker.start()

    tick = await worker.poll_and_execute_tick()
    assert tick["status"] == "completed"

    nodes = await _nodes(db, run_id)
    assert nodes["idea.generate"]["status"] == "SUCCEEDED"
    assert nodes["idea.generate"]["output_hashes"]
    assert nodes["idea.evaluate"]["status"] == "DISPATCHED"
    assert nodes["idea.evaluate"]["task_id"]

    # The envelope carried no inputs (root node) but the output artifact exists.
    assert await _artifact_count(db) == 1
    metrics = worker.metrics_snapshot()
    task_id = tick["task_id"]
    assert metrics["tasks"][task_id]["task_type"] == "studio.story.idea.generate"
    assert metrics["tasks"][task_id]["status"] == "completed"
    assert metrics["tasks"][task_id]["reconciled"] is True
    assert metrics["totals"]["processed"] == 1
    # Redaction-safe: no story content leaks into metrics.
    assert "Title 1" not in json.dumps(metrics)

    # Second tick executes the now-dispatched idea.evaluate (pure handler);
    # its IDEA checkpoint parks the node in WAITING_APPROVAL under the
    # default gated policy. Nothing else is claimable after that.
    tick2 = await worker.poll_and_execute_tick()
    assert tick2["status"] == "completed"
    assert (await _node(db, run_id, "idea.evaluate"))["status"] == "WAITING_APPROVAL"
    assert (await worker.poll_and_execute_tick())["status"] == "idle"
    assert worker.metrics_snapshot()["totals"]["processed"] == 2
    await worker.stop()


async def test_restart_recovery_reconciles_pending_completion(db, service):
    """Crash window: finalizer committed, reconciler never ran. A fresh worker
    start (StudioCompletionRecovery) re-drives the DAG idempotently."""
    _, episode_id, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)
    # Worker WITHOUT a reconciler: task finalizes, node stays DISPATCHED.
    worker = await _make_worker(
        db, model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)})
    )
    await worker.start()
    tick = await worker.poll_and_execute_tick()
    assert tick["status"] == "completed"
    assert (await _node(db, run_id, "idea.generate"))["status"] == "DISPATCHED"
    await worker.stop()

    # Restart: recovery sweep reconciles the pending completion.
    recovery = StudioCompletionRecovery(db.session_factory, service)
    recovered = await recovery.recover_pending_completions()
    assert recovered == 1
    nodes = await _nodes(db, run_id)
    assert nodes["idea.generate"]["status"] == "SUCCEEDED"
    assert nodes["idea.evaluate"]["status"] == "DISPATCHED"

    # Recovery is idempotent: a second sweep finds nothing to advance.
    assert await recovery.recover_pending_completions() == 0


async def test_duplicate_delivery_is_idempotent(db, studio):
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

    # Seed a claimed studio task row (submission adapter path).
    from windagent_core.contracts.workers.models import WorkSubmission
    from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter

    submission = SqlWorkSubmissionAdapter(db.session_factory, dedup_prefix="studio_submit")
    task_id = await submission.submit(
        WorkSubmission(
            prompt="[studio] test",
            task_id="stsk_dup_1",
            session_id="run_a5_dup",
            workflow_name="studio.story",
            idempotency_key="a5-dup-key",
            tool_name="studio.story.idea.evaluate",
            parameters={"studio_envelope": {"task_id": "stsk_dup_1"}},
        )
    )
    assert task_id == "stsk_dup_1"

    req = FinalizeTaskExecutionRequest(
        task_id=task_id,
        worker_id="wkr_a5",
        lease_id="lease_dup_1",
        fencing_token="fence_dup_1",
        expected_task_version=1,
        execution_result={"status": "SUCCEEDED"},
        terminal_state="completed",
    )
    async with SqlUnitOfWork(db.session_factory) as uow:
        first = await uow.finalize_task_execution(req)
        assert first.status == "COMPLETED"
    # Duplicate delivery: same task, same idempotency key -> already finalized.
    async with SqlUnitOfWork(db.session_factory) as uow:
        second = await uow.finalize_task_execution(req)
        assert second.already_finalized is True
    async with db.session_factory() as session:
        rows = await session.execute(
            text("SELECT COUNT(*) FROM task_execution_results_v2 WHERE task_id = :tid"),
            {"tid": task_id},
        )
        assert rows.scalar_one() == 1  # one atomic finalize, no double write


async def test_stale_fencing_token_rejected(db):
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

    from windagent_core.contracts.workers.models import WorkSubmission
    from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter

    submission = SqlWorkSubmissionAdapter(db.session_factory, dedup_prefix="studio_submit")
    task_id = await submission.submit(
        WorkSubmission(
            prompt="[studio] test",
            task_id="stsk_fence_1",
            session_id="run_a5_fence",
            workflow_name="studio.story",
            idempotency_key="a5-fence-key",
            tool_name="studio.story.idea.evaluate",
            parameters={},
        )
    )
    # A real claim creates the lease with the genuine fencing token.
    claimed = await SqlDurableTaskQueue(db.session_factory).claim_next("wkr_a5")
    assert claimed is not None and claimed.task_id == task_id

    req = FinalizeTaskExecutionRequest(
        task_id=task_id,
        worker_id="wkr_a5",
        lease_id=claimed.lease_id,
        fencing_token="fence_wrong",
        expected_task_version=1,
        execution_result={"status": "SUCCEEDED"},
        terminal_state="completed",
    )
    async with SqlUnitOfWork(db.session_factory) as uow:
        with pytest.raises(StaleResultRejectedError):
            await uow.finalize_task_execution(req)


async def test_worker_restart_claims_expired_lease(db, service):
    """Lease expiry/takeover: a new worker generation reclaims a task whose
    lease expired mid-execution (crash window before provider/finalize)."""
    from datetime import datetime, timedelta, timezone

    _, episode_id, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)
    worker = await _make_worker(
        db, model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)})
    )
    await worker.start()
    tick = await worker.poll_and_execute_tick()
    assert tick["status"] == "completed"
    await worker.stop()

    # Advance the DAG so the NEXT task (idea.evaluate) is dispatched, then
    # simulate a crashed worker mid-execution: claim it (lease created) and
    # let the lease expire without finalizing.
    recovery = StudioCompletionRecovery(db.session_factory, service)
    await recovery.recover_pending_completions()
    task_id = (await _node(db, run_id, "idea.evaluate"))["task_id"]
    assert task_id
    crashed = await SqlDurableTaskQueue(db.session_factory).claim_next("wkr_crashed")
    assert crashed is not None and crashed.task_id == task_id
    async with db.session_factory() as session:
        await session.execute(
            text(
                "UPDATE execution_leases SET expires_at = :past WHERE run_id = :tid "
                "AND status = 'active'"
            ),
            {"past": (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None), "tid": task_id},
        )
        await session.commit()

    # A fresh worker generation claims the expired lease (generation bump)
    # and re-executes with a NEW fencing token.
    worker2 = await _make_worker(
        db,
        studio_reconciler=service,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    await worker2.start()
    tick2 = await worker2.poll_and_execute_tick()
    assert tick2["status"] == "completed"
    assert tick2["task_id"] == task_id
    assert worker2.current_fencing_token != crashed.fencing_token
    await worker2.stop()
