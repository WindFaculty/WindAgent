"""Studio run-deadline enforcement tests (C7 attempt-8 forensic follow-up).

Covers the invariant: NO provider call may leave a Studio run in RUNNING
after its authoritative deadline. The orchestrator stamps every task
envelope with the absolute run deadline (created_at + budget); the worker
fails any task that would cross it — abandoning the in-flight provider
request via asyncio cancellation — and the reconciler terminalizes the run
(FAILED) instead of leaving a zombie RUNNING state.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import ExecutionRequest, RuntimeStatusEnum
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId, StudioRunId
from windagent_core.contracts.studio.models import StudioTaskEnvelope, StudioTaskStatus, StudioTaskType
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_intelligence.story.prompts.fixture import FixtureModelPort
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
from windagent_intelligence.video.ports import ModelCompletionResult
from windagent_orchestration.studio.service import StudioRunService, run_deadline
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_worker.runner import ProductionWorker
from windagent_worker.studio_runtime import (
    STUDIO_RUN_DEADLINE_EXCEEDED,
    StudioRuntimeAdapter,
)

import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401

BRIEF_DICT = {
    "brief_id": "brf_deadline_1",
    "title": "Deadline Episode",
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


class SlowModelPort:
    """Provider fake that deliberately hangs past any realistic budget."""

    fixture = False

    def __init__(self, delay: float = 5.0) -> None:
        self.delay = delay
        self.calls = 0
        self.completed = False

    async def complete(self, request) -> ModelCompletionResult:
        self.calls += 1
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.completed = False
            raise
        self.completed = True
        return ModelCompletionResult(
            capability=request.capability,
            content=json.dumps(FIXTURE_RESPONSE),
            finish_reason="stop",
            provider="slow-fake",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )


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


@pytest.fixture
def studio(db):
    """Throwaway StudioRunService used only to seed series/episodes."""
    return StudioRunService(
        lambda: StudioUnitOfWork(db.session_factory),
        StudioTaskSubmissionAdapter(db.session_factory),
        retry_budget=2,
    )


async def _seed_episode(db, service, *, brief: dict | None = None) -> tuple[SeriesProjectId, EpisodeId]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="dl-series-1", title="Deadline Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="dl-episode-1",
            series_id=series.series_id,
            title="Deadline Episode",
            episode_number=1,
            metadata={"creative_brief": brief} if brief else {},
        )
    )
    return series.series_id, episode.episode_id


async def _start_run_with_brief(db, service, brief: dict | None = None) -> tuple[SeriesProjectId, EpisodeId, StudioRunId]:
    series_id, episode_id = await _seed_episode(db, service, brief=brief)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="dl-run-1", episode_id=episode_id)
    )
    return series_id, episode_id, started.run_id


def _envelope(
    task_type: StudioTaskType,
    *,
    episode_id: EpisodeId,
    series_id: SeriesProjectId,
    run_id: StudioRunId | None = None,
    deadline: datetime | None = None,
) -> StudioTaskEnvelope:
    return StudioTaskEnvelope(
        task_type=task_type,
        studio_run_id=run_id or StudioRunId("run_dl_1"),
        dag_node_id="idea.generate",
        series_id=series_id,
        episode_id=episode_id,
        input_artifact_refs=[],
        idempotency_key="dl-key-1",
        deadline=deadline,
    )


async def _adapter(db, **kwargs) -> StudioRuntimeAdapter:
    registry = kwargs.pop("handler_registry", HANDLER_REGISTRY)
    return StudioRuntimeAdapter(
        handler_registry=registry,
        session_factory=db.session_factory,
        studio_uow_factory=lambda: StudioUnitOfWork(db.session_factory),
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


async def _make_worker(db, *, studio_reconciler=None, **runtime_kwargs):
    adapter = await _adapter(db, **runtime_kwargs)
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("studio", adapter)
    return ProductionWorker(
        name="deadline-test-worker",
        task_queue=SqlDurableTaskQueue(db.session_factory),
        execution_registry=registry,
        uow_factory=lambda: SqlUnitOfWork(db.session_factory),
        studio_reconciler=studio_reconciler,
    )


# ---------------------------------------------------------------------------
# Orchestrator side: envelope deadline
# ---------------------------------------------------------------------------


def test_run_deadline_helper_uses_env_budget(monkeypatch):
    created = datetime(2026, 8, 12, 16, 49, 36, tzinfo=timezone.utc)
    run = {"created_at": created}

    assert run_deadline(run) == created + timedelta(seconds=2700)

    monkeypatch.setenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", "120")
    assert run_deadline(run) == created + timedelta(seconds=120)

    monkeypatch.setenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", "0")
    assert run_deadline(run) == created + timedelta(seconds=1)  # clamped


async def test_envelope_carries_absolute_run_deadline(db, service, monkeypatch):
    monkeypatch.setenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", "300")
    _, episode_id, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)

    async with db.session_factory() as session:
        from windagent_storage.studio.repositories import SqlStudioRunRepository

        run = await SqlStudioRunRepository(session).get(run_id)

    envelope = service._envelope(
        run,
        {
            "task_type": "studio.story.idea.generate",
            "dag_node_id": "idea.generate",
            "input_hashes": [],
            "attempt": 1,
        },
    )
    assert envelope.deadline is not None
    expected = run["created_at"] + timedelta(seconds=300)
    assert abs((envelope.deadline - expected).total_seconds()) < 1


# ---------------------------------------------------------------------------
# Worker side: enforcement
# ---------------------------------------------------------------------------


async def test_slow_provider_past_deadline_fails_task(db, studio):
    """Provider hangs past the deadline: task FAILED, request abandoned,
    no artifacts, run-level invariant preserved."""
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    port = SlowModelPort(delay=5.0)
    adapter = await _adapter(db, model_port=port)
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        deadline=datetime.now(timezone.utc) + timedelta(milliseconds=400),
    )

    result = await _dispatch(adapter, envelope, "td1")
    data = result.result_data or {}

    assert result.status == RuntimeStatusEnum.FAILED
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert (result.error or "").startswith(STUDIO_RUN_DEADLINE_EXCEEDED)
    assert port.calls == 1  # provider call was started...
    assert port.completed is False  # ...and abandoned, not completed
    assert await _artifact_count(db) == 0


async def test_deadline_already_passed_fails_instantly(db, studio):
    """Retry dispatched after the run budget: fail fast, provider never called."""
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    port = SlowModelPort(delay=0.2)
    adapter = await _adapter(db, model_port=port)
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    result = await _dispatch(adapter, envelope, "td2")
    data = result.result_data or {}

    assert result.status == RuntimeStatusEnum.FAILED
    assert data.get("status") == StudioTaskStatus.FAILED.value
    assert (result.error or "").startswith(STUDIO_RUN_DEADLINE_EXCEEDED)
    assert port.calls == 0  # doomed provider call never started


async def test_fast_provider_completes_within_deadline(db, studio):
    """Generations inside the budget still succeed — no false timeouts."""
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
    )

    result = await _dispatch(adapter, envelope, "td3")
    data = result.result_data or {}

    assert result.status == RuntimeStatusEnum.COMPLETED
    assert data.get("status") == StudioTaskStatus.SUCCEEDED.value
    assert len(data["output_artifact_refs"]) == 1


async def test_no_deadline_preserves_legacy_behavior(db, studio):
    """Envelope without deadline: unbounded execution (unchanged contract)."""
    series_id, episode_id = await _seed_episode(db, studio, brief=BRIEF_DICT)
    adapter = await _adapter(
        db,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    envelope = _envelope(
        StudioTaskType.IDEA_GENERATE,
        episode_id=episode_id,
        series_id=series_id,
        deadline=None,
    )

    result = await _dispatch(adapter, envelope, "td4")
    assert result.status == RuntimeStatusEnum.COMPLETED


# ---------------------------------------------------------------------------
# End-to-end: hung provider + run deadline => terminal run, never a zombie
# ---------------------------------------------------------------------------


async def test_hung_provider_run_ends_terminal_not_zombie(db, service, monkeypatch):
    """The C7 attempt-8 scenario, reproduced in seconds: a provider that
    hangs past the run deadline must leave the run terminal (FAILED), not
    RUNNING forever. Retry budget exhausts; node parks on the last attempt."""
    monkeypatch.setenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", "1")
    _, _, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)
    worker = await _make_worker(
        db,
        studio_reconciler=service,
        model_port=SlowModelPort(delay=5.0),
    )
    await worker.start()

    tick1 = await worker.poll_and_execute_tick()
    assert tick1["status"] == "failed"
    assert STUDIO_RUN_DEADLINE_EXCEEDED in (tick1["error"] or "")
    node1 = await _node(db, run_id, "idea.generate")
    assert node1["status"] == "DISPATCHED"  # retry parked, not a zombie

    tick2 = await worker.poll_and_execute_tick()
    assert tick2["status"] == "failed"  # attempt 2: deadline already passed
    assert STUDIO_RUN_DEADLINE_EXCEEDED in (tick2["error"] or "")

    # retry_budget exhausted => run reaches a terminal state.
    async with db.session_factory() as session:
        from windagent_storage.studio.repositories import SqlStudioRunRepository

        run = await SqlStudioRunRepository(session).get(run_id)
    assert run["status"] == "FAILED"

    # No further claimable work; a fresh poll is idle, not a zombie loop.
    assert (await worker.poll_and_execute_tick())["status"] == "idle"
    await worker.stop()


async def test_worker_restart_after_deadline_kill_recovers_terminal_run(db, service, monkeypatch):
    """Late result fencing: a task failed by deadline can never be resurrected
    to SUCCEEDED by a later delivery — the run stays terminal across restart."""
    monkeypatch.setenv("WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS", "1")
    _, _, run_id = await _start_run_with_brief(db, service, brief=BRIEF_DICT)
    worker = await _make_worker(
        db,
        studio_reconciler=service,
        model_port=SlowModelPort(delay=5.0),
    )
    await worker.start()

    await worker.poll_and_execute_tick()  # attempt 1 -> deadline fail
    await worker.poll_and_execute_tick()  # attempt 2 -> deadline fail (budget exhausted)
    await worker.stop()

    async with db.session_factory() as session:
        from windagent_storage.studio.repositories import SqlStudioRunRepository

        run = await SqlStudioRunRepository(session).get(run_id)
    assert run["status"] == "FAILED"

    # Restart: a fresh worker claims nothing (no RUNNABLE nodes remain) and
    # cannot turn the terminal run back into COMPLETED.
    worker2 = await _make_worker(
        db,
        studio_reconciler=service,
        model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
    )
    await worker2.start()
    assert (await worker2.poll_and_execute_tick())["status"] == "idle"
    await worker2.stop()

    async with db.session_factory() as session:
        from windagent_storage.studio.repositories import SqlStudioRunRepository

        run = await SqlStudioRunRepository(session).get(run_id)
    assert run["status"] == "FAILED"
