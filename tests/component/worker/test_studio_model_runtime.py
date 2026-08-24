"""A6 — worker Story handler over the REAL model route (REAL_MODEL_RUNTIME_GATE surface).

A Plan B Story handler (``studio.story.idea.generate``) executes inside the
Studio worker runtime with ``RouteLockedModelPort`` — the real
``PreproductionModelPort`` over route lock + endpoint coordinator — and the
resulting artifact envelope persists complete route provenance
(model_route_id/provider_id/model_id/usage). Also covers the worker-side
runtime capability probe: honest source/reason/timestamp entries, Blender
detection, and certification fail-closed flags (fake runtime, fixture port,
non-durable model route, missing handlers).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import ExecutionRequest
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
)
from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId
from windagent_core.contracts.studio.models import (
    StudioRouteProvenance,
    StudioTaskEnvelope,
    StudioTaskResult,
    StudioTaskStatus,
    StudioTaskType,
)
from windagent_core.contracts.providers import ProviderResponse
from windagent_core.contracts.providers.usage import ProviderUsage
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
from windagent_orchestration.studio.service import StudioRunService
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.studio import (
    WorkerRuntimeCapabilityProbe,
)
from windagent_worker.studio_model_port import (
    RouteLockedModelPort,
    build_studio_ruleset,
)
from windagent_worker.composition import (
    CertificationPreflightError,
    WorkerContainer,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_worker.studio_runtime import StudioRuntimeAdapter
from tests.fakes.providers.routing import InMemoryLockStore

import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401

BRIEF_DICT = {
    "brief_id": "brf_a6_1",
    "title": "A6 Episode",
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

BINDING = {
    "endpoint_id": "ep-a6-stub",
    "binding_id": "bind-a6-stub",
    "provider_model_id": "stub-model-1",
    "provider_name": "stub-provider",
    "base_url": "https://stub.invalid/v1",
    "equivalence_level": "exact_revision",
    "is_active": True,
    "protocol_mode": "openai",
    "credential_ciphertext": "cipher:stub",
}


class StubState:
    async def is_available(self, endpoint_id: str) -> bool:
        return True

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        return None

    async def record_failure(self, endpoint_id: str, error_class: str, status_code) -> None:
        return None

    async def set_cooldown(self, endpoint_id: str, cooldown_until) -> None:
        return None


class StubQuota:
    async def get_quota_state(self, provider_id: str):
        return None

    async def update_quota_state(self, provider_id: str, snapshot) -> None:
        return None


class StubAttempts:
    def __init__(self) -> None:
        self.attempts: list[dict] = []

    async def record_attempt(self, **kwargs) -> str:
        self.attempts.append(kwargs)
        return f"attempt_{len(self.attempts)}"


class StubRegistry:
    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> list[dict]:
        return [BINDING]

    async def get_endpoint(self, endpoint_id: str):
        return BINDING


class StubProviderAdapter:
    """Controlled provider stub — non-certification tests only (A5 rule)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def generate(self, request, model_id: str | None = None) -> ProviderResponse:
        self.calls.append((request, model_id))
        return ProviderResponse(
            provider_id="stub-provider",
            provider_model_id=model_id,
            content=json.dumps(FIXTURE_RESPONSE),
            finish_reason="stop",
            usage=ProviderUsage(prompt_tokens=13, completion_tokens=29),
        )


def _build_real_port(stub: StubProviderAdapter) -> RouteLockedModelPort:
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: stub,
        endpoint_registry=StubRegistry(),
        endpoint_state=StubState(),
        quota_state=StubQuota(),
        attempt_log=StubAttempts(),
    )
    lock_service = RouteLockService(
        ruleset=build_studio_ruleset("canonical/a6-story"),
        lock_repository=InMemoryLockStore(),
    )
    return RouteLockedModelPort(lock_service, coordinator)


async def _seed(db) -> tuple[SeriesProjectId, EpisodeId]:
    service = StudioRunService(
        lambda: StudioUnitOfWork(db.session_factory),
        StudioTaskSubmissionAdapter(db.session_factory),
    )
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="a6-series", title="A6 Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="a6-episode",
            series_id=series.series_id,
            title="A6 Episode",
            episode_number=1,
            metadata={"creative_brief": BRIEF_DICT},
        )
    )
    return series.series_id, episode.episode_id


async def _dispatch(db, adapter: StudioRuntimeAdapter, envelope: StudioTaskEnvelope, task_id: str):
    request = ExecutionRequest(
        step_run_id=task_id,
        workflow_run_id=f"wf_{task_id}",
        tool_name=envelope.task_type.value,
        parameters={"studio_envelope": envelope.to_dict()},
        attempt_id="att_1",
        fencing_token=f"fence_{task_id}",
    )
    handle = await adapter.dispatch(request)
    return await adapter.get_result(handle)


# ---------------------------------------------------------------------------
# Worker Story handler crosses the real model route and persists provenance
# ---------------------------------------------------------------------------


async def test_worker_handler_invokes_real_route_and_persists_provenance():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        series_id, episode_id = await _seed(db)
        stub = StubProviderAdapter()
        port = _build_real_port(stub)
        adapter = StudioRuntimeAdapter(
            handler_registry=HANDLER_REGISTRY,
            session_factory=db.session_factory,
            model_port=port,
            studio_uow_factory=lambda: StudioUnitOfWork(db.session_factory),
        )
        envelope = StudioTaskEnvelope(
            task_type=StudioTaskType.IDEA_GENERATE,
            studio_run_id="run_a6_probe",
            dag_node_id="idea.generate",
            series_id=series_id,
            episode_id=episode_id,
            idempotency_key="a6-probe-1",
        )
        result = await _dispatch(db, adapter, envelope, "task_a6_1")

        # The stub provider was invoked exactly once through the coordinator.
        assert len(stub.calls) == 1
        provider_request, model_id = stub.calls[0]
        assert model_id == "stub-model-1"
        assert provider_request.system_instruction  # prompt content is real

        # The durable result carries complete route provenance.
        task_result = StudioTaskResult.model_validate(result.result_data)
        assert task_result.status == StudioTaskStatus.SUCCEEDED
        route: StudioRouteProvenance = task_result.route_provenance
        assert route.prompt_id == "story.ideation.generate"
        assert route.provider_id == "stub-provider"
        assert route.model_route_id  # the route lock id
        assert route.canonical_model_id == "canonical/a6-story"
        assert route.provider_model_id == "stub-model-1"
        assert route.model_id == "stub-model-1"
        assert route.endpoint_id == "ep-a6-stub"
        assert route.provider_binding_id == "bind-a6-stub"
        assert route.provider_attempt_id == "attempt_1"
        assert route.output_schema_contract.startswith("json:sha256:")
        assert route.usage["prompt_tokens"] == 13
        assert route.usage["completion_tokens"] == 29

        # The artifact envelope persisted model_route_id + provider + usage.
        async with db.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT model_route_id, provider_id, model_id, prompt_id, "
                        "canonical_model_id, provider_model_id, endpoint_id, "
                        "provider_binding_id, provider_attempt_id, "
                        "output_schema_contract "
                        "FROM studio_artifacts LIMIT 1"
                    )
                )
            ).one()
        assert row.model_route_id == route.model_route_id
        assert row.provider_id == "stub-provider"
        assert row.model_id == "stub-model-1"
        assert row.canonical_model_id == "canonical/a6-story"
        assert row.provider_model_id == "stub-model-1"
        assert row.endpoint_id == "ep-a6-stub"
        assert row.provider_binding_id == "bind-a6-stub"
        assert row.provider_attempt_id == route.provider_attempt_id
        assert row.output_schema_contract == route.output_schema_contract
        assert row.prompt_id == "story.ideation.generate"

        # Redaction: the persisted route receipt never contains prompt content.
        receipt_json = json.dumps(task_result.to_dict())
        assert "Title 1" not in receipt_json
        assert "hello model" not in receipt_json
    finally:
        await db.close()


async def test_same_task_retry_reuses_same_route_lock():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        series_id, episode_id = await _seed(db)
        port = _build_real_port(StubProviderAdapter())
        adapter = StudioRuntimeAdapter(
            handler_registry=HANDLER_REGISTRY,
            session_factory=db.session_factory,
            model_port=port,
            studio_uow_factory=lambda: StudioUnitOfWork(db.session_factory),
        )
        envelope = StudioTaskEnvelope(
            task_type=StudioTaskType.IDEA_GENERATE,
            studio_run_id="run_a6_retry",
            dag_node_id="idea.generate",
            series_id=series_id,
            episode_id=episode_id,
            idempotency_key="a6-probe-2",
        )
        r1 = StudioTaskResult.model_validate(
            (await _dispatch(db, adapter, envelope, "task_a6_r1")).result_data
        )
        r2 = StudioTaskResult.model_validate(
            (await _dispatch(db, adapter, envelope, "task_a6_r2")).result_data
        )
        assert r1.route_provenance.model_route_id == r2.route_provenance.model_route_id
        # Content-addressed idempotency: one artifact, reused by both results.
        assert r1.output_artifact_refs[0].artifact_id == r2.output_artifact_refs[0].artifact_id
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Worker-side runtime capability probe
# ---------------------------------------------------------------------------


async def test_capability_probe_reports_real_composition():
    probe = WorkerRuntimeCapabilityProbe(
        db=object(),
        task_queue=object(),
        route_lock_service=_build_real_port(StubProviderAdapter())._route_lock_service,
        coordinator=object(),
        handler_registry=HANDLER_REGISTRY,
        model_port=object(),
    )
    profile = await probe.get_capabilities()
    by_name = {c.name: c for c in profile.capabilities}
    assert by_name["durable_db"].status.value == "AVAILABLE"
    assert by_name["queue"].status.value == "AVAILABLE"
    assert by_name["worker"].status.value == "AVAILABLE"
    assert by_name["story_engine"].status.value == "AVAILABLE"
    assert by_name["model_route"].status.value == "UNAVAILABLE"  # in-memory lock store
    assert by_name["model_route"].reason  # honest reason, not invented
    assert by_name["unreal"].status.value == "UNAVAILABLE"
    # Every capability carries source + timestamp.
    for cap in profile.capabilities:
        assert cap.source
        assert cap.discovered_at is not None


async def test_capability_probe_blender_detection(monkeypatch, tmp_path):
    monkeypatch.delenv("WINDAGENT_BLENDER_EXECUTABLE", raising=False)
    monkeypatch.setattr(
        "windagent_providers.studio.capability_probe.shutil.which", lambda _: None
    )
    probe = WorkerRuntimeCapabilityProbe()
    profile = await probe.get_capabilities()
    blender = profile.by_name("blender")
    assert blender.status.value == "UNAVAILABLE"

    fake_blender = tmp_path / "blender.exe"
    fake_blender.write_text("", encoding="utf-8")
    monkeypatch.setenv("WINDAGENT_BLENDER_EXECUTABLE", str(fake_blender))
    profile = await probe.get_capabilities()
    blender = profile.by_name("blender")
    assert blender.status.value == "AVAILABLE"
    assert blender.metadata["executable"] == "blender.exe"


async def test_certification_profile_fails_closed():
    from windagent_intelligence.story.prompts.fixture import FixtureModelPort

    probe = WorkerRuntimeCapabilityProbe(
        handler_registry=HANDLER_REGISTRY,
        model_port=FixtureModelPort(),
        fake_runtime_active=True,
        certification_mode=True,
    )
    profile = await probe.get_capabilities()
    assert profile.certification_mode is True
    assert "fake_runtime" in profile.fail_closed_flags
    assert "fixture_model_port" in profile.fail_closed_flags
    assert "non_durable_model_route" in profile.fail_closed_flags
    assert profile.is_fail_closed_ok is False


async def test_clean_certification_profile_has_no_flags(monkeypatch):
    monkeypatch.delenv("WINDAGENT_BLENDER_EXECUTABLE", raising=False)
    probe = WorkerRuntimeCapabilityProbe(
        db=object(),
        task_queue=object(),
        route_lock_service=_build_real_port(StubProviderAdapter())._route_lock_service,
        coordinator=object(),
        handler_registry=HANDLER_REGISTRY,
        model_port=object(),
        certification_mode=True,
    )
    profile = await probe.get_capabilities()
    # model_route is in-memory in tests -> honest non_durable flag.
    assert "fake_runtime" not in profile.fail_closed_flags
    assert "fixture_model_port" not in profile.fail_closed_flags
    assert "non_durable_model_route" in profile.fail_closed_flags


def test_certification_worker_preflight_rejects_incomplete_composition(monkeypatch):
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")
    monkeypatch.delenv("WIND_STUDIO_CERTIFICATION", raising=False)
    monkeypatch.delenv("WINDAGENT_STUDIO_RUNTIME", raising=False)
    monkeypatch.delenv("WINDAGENT_STUDIO_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("WINDAGENT_STUDIO_CANONICAL_MODEL", raising=False)
    monkeypatch.delenv("WINDAGENT_DATABASE_URL", raising=False)

    container = WorkerContainer()
    with pytest.raises(CertificationPreflightError) as exc_info:
        container.validate_certification_preflight()

    message = str(exc_info.value)
    assert "WINDAGENT_STUDIO_RUNTIME=1" in message
    assert "WINDAGENT_STUDIO_MODEL_ROUTE=1" in message
    assert "canonical model" in message
    assert "durable DB" in message
    assert "StudioRuntimeAdapter" in message
    assert "StudioCompletionReconciler" in message
    assert "RouteLockedModelPort" in message
