"""P0.4 — Series/Episode product completion: metadata authority + preflight.

Covers:

- Series/Episode edit mutations (PATCH semantics: title/description +
  ``metadata_patch`` merge) with server-side metadata validation of the
  known presentation keys;
- Generation-affecting episode fields are IMMUTABLE once the episode leaves
  DRAFT (no silent mutation of an existing run's context);
- P0.4.1 Story Start preflight: truthful per-check report and the
  START_BLOCKED gate on the start endpoint when requirements are missing.
"""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.routers.v3.studio.dependencies import (
    get_studio_application_service,
)
from windagent_api.routers.v3.studio.episodes import router_episode
from windagent_api.routers.v3.studio.runs import router_runs_start
from windagent_api.services.studio_preflight import (
    CHECK_NAMES,
    REQUIRED_STORY_CAPABILITIES,
    StoryStartPreflight,
)
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    UpdateEpisodeCommand,
    UpdateSeriesCommand,
)
from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.lifecycle import EpisodeState
from windagent_core.domain.studio.series import SeriesProject
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from windagent_orchestration.studio.service import StudioRunService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

BRIEF = {
    "brief_id": "brf_p04",
    "title": "P04 Brief",
    "genre": "fantasy",
    "logline": "A kite learns to fly.",
    "tone": "warm",
    "audience": "kids",
    "language": "vi",
}


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


# ---------------------------------------------------------------------------
# Metadata authority on create + update_series / update_episode
# ---------------------------------------------------------------------------


async def test_create_rejects_invalid_known_metadata(service):
    with pytest.raises(StudioValidationError):
        await service.create_series(
            CreateSeriesCommand(
                idempotency_key="p04-bad-policy",
                title="Bad Policy",
                metadata={"approval_policy": "WHENEVER"},
            )
        )
    with pytest.raises(StudioValidationError):
        await service.create_series(
            CreateSeriesCommand(
                idempotency_key="p04-bad-genre",
                title="Bad Genre",
                metadata={"genre": 42},
            )
        )


async def test_update_series_merges_metadata(db, service):
    created = await service.create_series(
        CreateSeriesCommand(
            idempotency_key="p04-series",
            title="Original",
            description="v1",
            metadata={"language": "vi", "genre": "fantasy"},
        )
    )
    updated = await service.update_series(
        UpdateSeriesCommand(
            idempotency_key="p04-series-edit-1",
            series_id=created.series_id,
            title="Renamed",
            description="v2",
            metadata_patch={"tone": "cozy", "approval_policy": "AUTO"},
        )
    )
    assert updated.title == "Renamed"

    async with StudioUnitOfWork(db.session_factory) as uow:
        view = await uow.series.get(created.series_id)
    assert view.title == "Renamed"
    assert view.description == "v2"
    # merge, not replace
    assert view.metadata["language"] == "vi"
    assert view.metadata["tone"] == "cozy"


async def test_update_episode_draft_editable_then_immutable(db, service):
    created_series = await service.create_series(
        CreateSeriesCommand(idempotency_key="p04-s2", title="S2")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="p04-e2",
            series_id=created_series.series_id,
            title="Ep2",
            metadata={"creative_brief": BRIEF},
        )
    )

    # DRAFT edit: merge works and bumps the optimistic version.
    result = await service.update_episode(
        UpdateEpisodeCommand(
            idempotency_key="p04-e2-edit-1",
            episode_id=episode.episode_id,
            metadata_patch={"logline": "Updated logline", "target_duration": 300},
        )
    )
    assert result.state == "DRAFT"
    assert result.optimistic_version >= 1

    # Leave DRAFT (as a run would) then try to change generation inputs.
    async with StudioUnitOfWork(db.session_factory) as uow:
        aggregate = await uow.episodes.get(episode.episode_id)
        moved = aggregate.transition_to(EpisodeState.IDEA_REVIEW)
        await uow.episodes.save(moved)
        await uow.commit()

    from windagent_core.contracts.studio.errors import StudioValidationError as SVE

    with pytest.raises(SVE) as exc_info:
        await service.update_episode(
            UpdateEpisodeCommand(
                idempotency_key="p04-e2-edit-2",
                episode_id=episode.episode_id,
                metadata_patch={"creative_brief": {**BRIEF, "logline": "changed"}},
            )
        )
    details = exc_info.value.details or {}
    assert details.get("immutable_fields") == ["creative_brief"]

    # Title remains editable (presentation only), even outside DRAFT.
    retitled = await service.update_episode(
        UpdateEpisodeCommand(
            idempotency_key="p04-e2-edit-3",
            episode_id=episode.episode_id,
            title="Ep2 renamed",
        )
    )
    assert retitled.optimistic_version >= 1


async def test_stale_write_protected_edit(db, service):
    created_series = await service.create_series(
        CreateSeriesCommand(idempotency_key="p04-s3", title="S3")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="p04-e3",
            series_id=created_series.series_id,
            title="Ep3",
        )
    )
    from windagent_core.contracts.studio.errors import StudioStaleRevisionError

    with pytest.raises(StudioStaleRevisionError):
        await service.update_episode(
            UpdateEpisodeCommand(
                idempotency_key="p04-e3-edit-stale",
                episode_id=episode.episode_id,
                title="Too late",
                expected_optimistic_version=99,
            )
        )


# ---------------------------------------------------------------------------
# P0.4.1 — Story Start preflight
# ---------------------------------------------------------------------------


class _StaticRepo:
    def __init__(self, value):
        self._value = value

    async def get(self, _id):
        return self._value


class _FakeProviders:
    def __init__(self, providers):
        self._providers = providers

    def list_providers(self):
        return self._providers


class _FakeCapability:
    def __init__(self, available: bool):
        self.available = available

    async def get_capabilities(self):
        from windagent_core.contracts.studio.capabilities import (
            CapabilityStatus,
            RuntimeCapability,
            RuntimeCapabilityProfile,
        )

        status = CapabilityStatus.AVAILABLE if self.available else CapabilityStatus.UNAVAILABLE
        return RuntimeCapabilityProfile(
            capabilities=[
                RuntimeCapability(name="model_route", status=status, source="fake"),
                RuntimeCapability(name="story_engine", status=status, source="fake"),
            ]
        )


def _ruleset_covering_all_roles() -> RoutingRuleSet:
    rules = [
        RoutingRule(
            rule_id=f"role-{capability}",
            rule_version=1,
            canonical_model_id=f"test/model-{capability}",
            task_labels=[capability],
        )
        for capability in REQUIRED_STORY_CAPABILITIES
    ]
    return RoutingRuleSet(rules=rules)


def _episode_with_brief() -> Episode:
    return Episode(
        episode_id=EpisodeId("ep-p04-preflight"),
        series_id=SeriesProjectId("srs-p04-preflight"),
        title="Preflight Ep",
        metadata={"creative_brief": BRIEF},
    )


async def test_preflight_reports_every_missing_requirement():
    preflight = StoryStartPreflight(
        episodes_repo=_StaticRepo(None),
        series_repo=_StaticRepo(None),
        provider_management_service=_FakeProviders([]),
        route_lock_service=RouteLockService(ruleset=RoutingRuleSet(rules=[])),
        capability_provider=None,
    )
    report = await preflight.run("ep-missing")
    assert report["ready"] is False
    assert [c["name"] for c in report["checks"]] == list(CHECK_NAMES)
    failed = {c["name"] for c in report["checks"] if c["status"] == "FAIL"}
    warned = {c["name"] for c in report["checks"] if c["status"] == "WARN"}
    # Hard failures block; worker heartbeat absence is an honest WARN.
    assert {
        "episode_exists",
        "creative_brief_valid",
        "provider_configured",
        "routing_rules_resolve",
    } <= failed
    assert "worker_capability_available" in warned


async def test_preflight_passes_with_full_configuration():
    series = SeriesProject(series_id=SeriesProjectId("srs-p04-ok"), title="OK")
    lock_service = RouteLockService(ruleset=_ruleset_covering_all_roles())
    preflight = StoryStartPreflight(
        episodes_repo=_StaticRepo(_episode_with_brief()),
        series_repo=_StaticRepo(series),
        provider_management_service=_FakeProviders(
            [{"enabled": True, "endpoints": [{"is_configured": True}]}]
        ),
        route_lock_service=lock_service,
        capability_provider=_FakeCapability(available=True),
    )
    report = await preflight.run(_episode_with_brief().episode_id)
    assert report["ready"] is True, report


async def test_start_endpoint_returns_start_blocked_when_not_ready():
    class NotReadyService:
        async def preflight_start(self, *, episode_id):
            return {
                "episode_id": str(episode_id),
                "ready": False,
                "checks": [
                    {"name": "provider_configured", "status": "FAIL", "detail": "none"},
                    {"name": "routing_rules_resolve", "status": "FAIL", "detail": "all"},
                ],
            }

        async def get_episode(self, *, episode_id):  # no active run
            return {"active_run_id": None}

        async def parse_id(self, id_cls, value, label):  # pragma: no cover
            return value

        async def start_or_resume_run(self, **_kwargs):  # pragma: no cover
            raise AssertionError("start must be blocked before the orchestrator")

    app = FastAPI()
    app.include_router(router_runs_start, prefix="/api/v3/studio")
    app.include_router(router_episode, prefix="/api/v3/studio")
    app.dependency_overrides[get_studio_application_service] = lambda: NotReadyService()
    client = TestClient(app)

    response = client.post(
        "/api/v3/studio/episodes/ep-x/runs",
        json={},
        headers={"X-Idempotency-Key": "p04-start-blocked-1"},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "START_BLOCKED"
    assert len(payload["reasons"]) == 2
