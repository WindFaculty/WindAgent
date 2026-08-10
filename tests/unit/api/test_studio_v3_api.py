"""
Plan C1 gate tests: modular /api/v3/studio surface (STUDIO_API_GATE).

Two layers:
1. Production composition (no dependency overrides): the API fails closed
   with CAPABILITY_UNAVAILABLE until Plan A handoff wires real ports, the
   capability/readiness views report observed state, V2 deprecation metadata
   is additive, and V2 keeps working.
2. Contract layer (dependency overrides with fakes implementing the frozen
   Plan A ports): route/method/status, validation/redaction, error mapping,
   idempotent replay/mismatch, optimistic conflicts, approval/lock stale
   hashes, actor passthrough, run links and event cursors.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app
from windagent_api.routers.v3.studio.dependencies import get_studio_application_service
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.events.studio import StudioEventEnvelope
from tests.fakes.studio_fakes import (
    FakeApprovalRepository,
    FakeArtifactRepository,
    FakeCapabilityPort,
    FakeEpisodeRepository,
    FakeEventQueryPort,
    FakeRevisionRepository,
    FakeRunQueryPort,
    FakeSeriesRepository,
    FakeStudioOrchestrator,
)

HASH = "a" * 64

_key_counter = 0


def _idem() -> str:
    global _key_counter
    _key_counter += 1
    return f"idem_c1_{_key_counter:06d}"


def _build_fake_service() -> StudioApplicationService:
    orchestrator = FakeStudioOrchestrator()
    return StudioApplicationService(
        orchestrator=orchestrator,
        run_query=FakeRunQueryPort(orchestrator),
        event_query=FakeEventQueryPort(orchestrator),
        capability=FakeCapabilityPort(),
        series_repo=FakeSeriesRepository(orchestrator),
        episodes_repo=FakeEpisodeRepository(orchestrator),
        revisions_repo=FakeRevisionRepository(orchestrator),
        artifacts_repo=FakeArtifactRepository(),
        approvals_repo=FakeApprovalRepository(orchestrator),
    )


class TestV3ProductionComposition:
    """Real container, no overrides: honest fail-closed behavior pre-A-handoff."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'c1_prod.db'}")
        with TestClient(app) as test_client:
            yield test_client

    def test_v3_mutations_fail_closed_without_a_handoff(self, client):
        res = client.post(
            "/api/v3/studio/series",
            headers={"X-Idempotency-Key": _idem()},
            json={"title": "Chuỗi phim"},
        )
        assert res.status_code == 503, res.text
        body = res.json()
        assert body["studio_code"] == "CAPABILITY_UNAVAILABLE"
        assert body["status"] == 503
        assert body["retryable"] is True

    def test_v3_reads_hit_real_storage(self, client):
        res = client.get("/api/v3/studio/series")
        assert res.status_code == 200, res.text
        assert res.json()["items"] == []

    async def test_v3_reads_serve_real_persisted_rows(self, tmp_path, monkeypatch):
        """A3 persistence is real: rows written through StudioUnitOfWork are
        served by the V3 read endpoints after API startup."""
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'c1_seed.db'}"
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", db_url)

        import windagent_storage.orm.studio_models  # noqa: F401  (registers tables)
        from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId
        from windagent_core.domain.studio.episode import Episode
        from windagent_core.domain.studio.series import SeriesProject
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM
        from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

        db = DatabaseManager(db_url)
        await db.upgrade_to_head(BaseORM.metadata)
        try:
            async with StudioUnitOfWork(db.session_factory) as uow:
                series = SeriesProject(
                    series_id=SeriesProjectId("series_real_0001"),
                    title="Chuỗi phim thỏ và diều (thật)",
                    description="Dữ liệu thật từ A3",
                )
                await uow.series.save(series)
                await uow.episodes.save(
                    Episode(
                        episode_id=EpisodeId("episode_real_0001"),
                        series_id=series.series_id,
                        title="Tập 1: Diều giấy",
                        episode_number=1,
                    )
                )
                await uow.commit()
        finally:
            await db.close()

        with TestClient(app) as test_client:
            listed = test_client.get("/api/v3/studio/series")
            assert listed.status_code == 200, listed.text
            items = listed.json()["items"]
            assert len(items) == 1
            assert items[0]["series_id"] == "series_real_0001"
            assert items[0]["title"] == "Chuỗi phim thỏ và diều (thật)"

            episodes = test_client.get(
                "/api/v3/studio/series/series_real_0001/episodes"
            )
            assert episodes.status_code == 200, episodes.text
            assert episodes.json()["items"][0]["episode_id"] == "episode_real_0001"

            detail = test_client.get("/api/v3/studio/episodes/episode_real_0001")
            assert detail.status_code == 200, detail.text
            assert detail.json()["state"] == "DRAFT"

            missing = test_client.get("/api/v3/studio/episodes/episode_real_9999")
            assert missing.status_code == 404
            assert missing.json()["studio_code"] == "NOT_FOUND"

    def test_capabilities_view_reports_real_state(self, client):
        res = client.get("/api/v3/studio/capabilities")
        assert res.status_code == 200, res.text
        body = res.json()
        by_name = {c["name"]: c for c in body["capabilities"]}
        assert by_name["durable_db"]["status"] == "AVAILABLE"
        assert by_name["studio_orchestration"]["status"] == "UNAVAILABLE"
        assert "A4" in by_name["studio_orchestration"]["reason"]
        assert by_name["story_engine"]["status"] == "UNAVAILABLE"
        assert body["fail_closed_flags"] == []
        assert body["schema_version"] == "studio.capability/v1"

    def test_readiness_view(self, client):
        res = client.get("/api/v3/studio/readiness")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] in {"DEGRADED", "UNAVAILABLE"}
        assert body["capabilities"]["durable_db"] == "AVAILABLE"
        assert "capabilities" in body

    def test_v3_surface_survives_api_restart(self, tmp_path, monkeypatch):
        db = tmp_path / "c1_restart.db"
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db}")
        with TestClient(app) as first:
            assert first.get("/api/v3/studio/capabilities").status_code == 200
            assert first.get("/api/v3/studio/readiness").status_code == 200
        with TestClient(app) as second:
            assert second.get("/api/v3/studio/capabilities").status_code == 200
            body = second.get("/api/v3/studio/capabilities").json()
            by_name = {c["name"]: c for c in body["capabilities"]}
            assert by_name["durable_db"]["status"] == "AVAILABLE"

    def test_v2_deprecation_metadata_is_additive(self, client):
        res = client.get("/api/v2/does-not-exist-anywhere")
        assert res.status_code == 404
        assert res.headers.get("Deprecation") == "true"
        assert res.headers.get("X-WindAgent-Deprecation") == "v2"
        assert res.headers.get("X-WindAgent-V3-Studio") == "/api/v3/studio"

    def test_v1_tombstone_untouched(self, client):
        res = client.get("/api/v1/anything")
        assert res.status_code == 410
        assert "Deprecation" not in res.headers


class TestV3ContractWithFakes:
    """Frozen surface contract against fakes implementing the A ports."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'c1_contract.db'}")
        service = _build_fake_service()
        app.dependency_overrides[get_studio_application_service] = lambda: service
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()

    def _create_series(self, client, title="Chuỗi phim thỏ và diều"):
        return client.post(
            "/api/v3/studio/series",
            headers={"X-Idempotency-Key": _idem()},
            json={"title": title, "description": "Truyện thiếu nhi"},
        )

    def _create_episode(self, client, series_id, number=1):
        return client.post(
            f"/api/v3/studio/series/{series_id}/episodes",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "series_id": series_id,
                "title": "Tập 1: Chiếc diều giấy",
                "episode_number": number,
            },
        )

    # -- series ------------------------------------------------------------

    def test_create_series_201_no_sample_id(self, client):
        res = self._create_series(client)
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["series_id"].startswith("series_")
        assert body["title"] == "Chuỗi phim thỏ và diều"
        assert body["series_url"].startswith("/api/v3/studio/series/")
        assert "proj-alpha" not in res.text and "vp_001" not in res.text

    def test_create_series_requires_idempotency_key(self, client):
        res = client.post("/api/v3/studio/series", json={"title": "X"})
        assert res.status_code == 422
        body = res.json()
        assert body["studio_code"] == "VALIDATION_ERROR"
        assert "X-Idempotency-Key" in body["detail"]

    def test_list_and_get_series(self, client):
        created = self._create_series(client).json()
        listed = client.get("/api/v3/studio/series")
        assert listed.status_code == 200
        assert any(i["series_id"] == created["series_id"] for i in listed.json()["items"])
        detail = client.get(f"/api/v3/studio/series/{created['series_id']}")
        assert detail.status_code == 200
        assert detail.json()["title"] == created["title"]
        assert detail.json()["series_url"].endswith(created["series_id"])

    def test_get_missing_series_404(self, client):
        res = client.get("/api/v3/studio/series/series_9999")
        assert res.status_code == 404
        assert res.json()["studio_code"] == "NOT_FOUND"

    def test_invalid_id_422(self, client):
        res = client.get("/api/v3/studio/series/%20")
        assert res.status_code == 422
        assert res.json()["studio_code"] == "VALIDATION_ERROR"

    # -- episodes ----------------------------------------------------------

    def test_create_list_get_episode(self, client):
        series_id = self._create_series(client).json()["series_id"]
        res = self._create_episode(client, series_id)
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["state"] == "DRAFT"
        episode_id = body["episode_id"]

        listed = client.get(f"/api/v3/studio/series/{series_id}/episodes")
        assert listed.status_code == 200
        assert any(i["episode_id"] == episode_id for i in listed.json()["items"])

        detail = client.get(f"/api/v3/studio/episodes/{episode_id}")
        assert detail.status_code == 200
        view = detail.json()
        assert view["state"] == "DRAFT"
        assert view["optimistic_version"] == 0
        assert view["series_id"] == series_id
        assert "artifact_summary" in view and "approvals" in view
        assert view["run_url"] is None

    def test_episode_missing_series_404(self, client):
        res = client.get("/api/v3/studio/episodes/episode_9999")
        assert res.status_code == 404
        assert res.json()["studio_code"] == "NOT_FOUND"

    def test_create_episode_series_mismatch_422(self, client):
        series_id = self._create_series(client).json()["series_id"]
        res = client.post(
            f"/api/v3/studio/series/{series_id}/episodes",
            headers={"X-Idempotency-Key": _idem()},
            json={"series_id": "series_OTHER", "title": "Sai series", "episode_number": 1},
        )
        assert res.status_code == 422
        assert res.json()["studio_code"] == "VALIDATION_ERROR"

    # -- runs --------------------------------------------------------------

    def test_start_run_returns_202_durable_link(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/runs",
            headers={"X-Idempotency-Key": _idem()},
            json={},
        )
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["run_id"].startswith("run_")
        assert body["resuming"] is False
        assert body["run_url"] == f"/api/v3/studio/runs/{body['run_id']}"
        assert res.headers["Location"] == body["run_url"]

    def test_run_status_and_events_cursor(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        run_id = client.post(
            f"/api/v3/studio/episodes/{episode_id}/runs",
            headers={"X-Idempotency-Key": _idem()},
            json={},
        ).json()["run_id"]

        run = client.get(f"/api/v3/studio/runs/{run_id}")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "RUNNING"
        assert run.json()["run_url"].endswith(run_id)
        assert "dag" in run.json()

        events = client.get(f"/api/v3/studio/runs/{run_id}/events?after=0")
        assert events.status_code == 200
        assert events.json()["latest_sequence"] == 0
        assert events.json()["events"] == []

        missing = client.get("/api/v3/studio/runs/run_9999")
        assert missing.status_code == 404

    def test_run_events_poll_with_seeded_cursor(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        run_id = client.post(
            f"/api/v3/studio/episodes/{episode_id}/runs",
            headers={"X-Idempotency-Key": _idem()},
            json={},
        ).json()["run_id"]

        # Seed the fake event stream through the same query port instance.
        def _seed_events():
            service = _build_fake_service()
            for seq in (1, 2):
                service.event_query.events.append(
                    StudioEventEnvelope(
                        event_type="studio.run.failed" if seq == 2 else "studio.idea.candidates_generated",
                        aggregate_id=episode_id,
                        sequence=seq,
                        studio_run_id=run_id,
                    )
                )
            return service

        app.dependency_overrides[get_studio_application_service] = _seed_events
        try:
            events = client.get(f"/api/v3/studio/runs/{run_id}/events?after=1")
            assert events.status_code == 200
            body = events.json()
            assert body["latest_sequence"] == 2
            assert [e["sequence"] for e in body["events"]] == [2]
        finally:
            app.dependency_overrides[get_studio_application_service] = lambda: _build_fake_service()

    # -- decisions: idea selection ----------------------------------------

    def test_select_idea_happy_path_and_replay(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        key = _idem()
        payload = {
            "episode_id": episode_id,
            "revision_id": "revision_0001",
            "candidate_id": "candidate_rabbit_kite",
            "expected_content_hash": HASH,
            "expected_optimistic_version": 0,
        }
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": key},
            json=payload,
        )
        assert res.status_code == 200, res.text
        assert res.json()["candidate_id"] == "candidate_rabbit_kite"

        # Same key + same body replays the original result.
        replay = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": key},
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json() == res.json()

    def test_select_idea_hash_mismatch_409(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": episode_id,
                "revision_id": "revision_0001",
                "candidate_id": "candidate_x",
                "expected_content_hash": "b" * 64,
                "expected_optimistic_version": 0,
            },
        )
        assert res.status_code == 409
        assert res.json()["studio_code"] == "ARTIFACT_HASH_MISMATCH"

    def test_select_idea_idempotency_mismatch_409(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        key = _idem()
        base = {
            "episode_id": episode_id,
            "revision_id": "revision_0001",
            "expected_content_hash": HASH,
            "expected_optimistic_version": 0,
        }
        first = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": key},
            json={**base, "candidate_id": "candidate_a"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": key},
            json={**base, "candidate_id": "candidate_b"},
        )
        assert second.status_code == 409
        assert second.json()["studio_code"] == "IDEMPOTENCY_MISMATCH"

    def test_idea_selection_stale_version_409(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/idea-selection",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": episode_id,
                "revision_id": "revision_0001",
                "candidate_id": "candidate_c",
                "expected_content_hash": HASH,
                "expected_optimistic_version": 42,
            },
        )
        assert res.status_code == 409
        body = res.json()
        assert body["studio_code"] == "STALE_REVISION"
        assert body["details"]["expected_version"] == 42

    # -- decisions: approvals ---------------------------------------------

    def test_approval_actor_passthrough_and_result(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        revision_id = self._derive(client, series_id, episode_id)["revision_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/approvals",
            headers={"X-Idempotency-Key": _idem(), "X-WindAgent-Actor": "minh"},
            json={
                "episode_id": episode_id,
                "revision_id": revision_id,
                "checkpoint": "IDEA",
                "artifact_hash": HASH,
                "decision": "REJECTED",
                "reason": "Cần ý tưởng bay cao hơn",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["checkpoint"] == "IDEA"
        assert body["next_state"] == "REVISING"
        assert body["awaiting_approval"] is True

        # The decision is durable in the fake approval store and visible on detail.
        detail = client.get(f"/api/v3/studio/episodes/{episode_id}")
        approvals = detail.json()["approvals"]
        assert len(approvals) == 1
        assert approvals[0]["actor"] == "minh"
        assert approvals[0]["decision"] == "REJECTED"

    def _derive(self, client, series_id, episode_id, parent="revision_0001", hash_value=None):
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/revisions",
            headers={"X-Idempotency-Key": _idem(), "X-WindAgent-Actor": "minh"},
            json={
                "episode_id": episode_id,
                "series_id": series_id,
                "parent_revision_id": parent,
                "new_content_hash": hash_value or "c" * 64,
                "summary": "Sửa theo góp ý",
                "expected_optimistic_version": 0,
            },
        )
        assert res.status_code == 201, res.text
        return res.json()

    def test_approval_episode_mismatch_422(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/approvals",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": "episode_OTHER",
                "revision_id": "revision_0001",
                "checkpoint": "IDEA",
                "artifact_hash": HASH,
                "decision": "APPROVED",
            },
        )
        assert res.status_code == 422
        assert res.json()["studio_code"] == "VALIDATION_ERROR"

    # -- decisions: revisions ---------------------------------------------

    def test_derive_revision_201(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/revisions",
            headers={"X-Idempotency-Key": _idem(), "X-WindAgent-Actor": "minh"},
            json={
                "episode_id": episode_id,
                "series_id": series_id,
                "parent_revision_id": "revision_0001",
                "new_content_hash": "c" * 64,
                "summary": "Sửa theo góp ý: diều bay qua sông",
                "expected_optimistic_version": 0,
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["revision_id"].startswith("revision_")
        assert body["parent_revision_id"] == "revision_0001"

    def test_derive_revision_locked_parent_409(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        revision_id = self._derive(client, series_id, episode_id)["revision_id"]
        lock = client.post(
            f"/api/v3/studio/episodes/{episode_id}/screenplay-lock",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": episode_id,
                "revision_id": revision_id,
                "expected_content_hash": HASH,
                "expected_optimistic_version": 0,
            },
        )
        assert lock.status_code == 200, lock.text
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/revisions",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": episode_id,
                "series_id": series_id,
                "parent_revision_id": revision_id,
                "new_content_hash": "e" * 64,
                "expected_optimistic_version": 0,
            },
        )
        assert res.status_code == 409
        assert res.json()["studio_code"] == "LOCKED_REVISION"

    # -- decisions: screenplay lock ---------------------------------------

    def test_lock_screenplay_receipt(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        res = client.post(
            f"/api/v3/studio/episodes/{episode_id}/screenplay-lock",
            headers={"X-Idempotency-Key": _idem()},
            json={
                "episode_id": episode_id,
                "revision_id": "revision_0001",
                "expected_content_hash": HASH,
                "expected_optimistic_version": 0,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["state"] == "LOCKED"
        assert body["lock_receipt_artifact_id"]

    def test_lock_screenplay_stale_hash_409_after_lock(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]
        revision_id = self._derive(client, series_id, episode_id)["revision_id"]
        payload = {
            "episode_id": episode_id,
            "revision_id": revision_id,
            "expected_content_hash": HASH,
            "expected_optimistic_version": 0,
        }
        first = client.post(
            f"/api/v3/studio/episodes/{episode_id}/screenplay-lock",
            headers={"X-Idempotency-Key": _idem()},
            json=payload,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v3/studio/episodes/{episode_id}/screenplay-lock",
            headers={"X-Idempotency-Key": _idem()},
            json={**payload, "expected_content_hash": "d" * 64},
        )
        assert second.status_code == 409
        assert second.json()["studio_code"] == "LOCKED_REVISION"

    # -- artifacts ---------------------------------------------------------

    def test_artifact_views(self, client):
        series_id = self._create_series(client).json()["series_id"]
        episode_id = self._create_episode(client, series_id).json()["episode_id"]

        def _seed_artifact():
            service = _build_fake_service()
            from windagent_core.domain.studio.artifact import StoryArtifactEnvelope

            service.artifacts_repo.artifacts["artifact_0001"] = StoryArtifactEnvelope(
                artifact_id="artifact_0001",
                artifact_type="IdeaCandidateSet",
                series_id=series_id,
                episode_id=episode_id,
                revision_id="revision_0001",
                content_hash=HASH,
                content={"candidates": [{"id": "candidate_rabbit_kite", "title": "Thỏ và chiếc diều"}]},
            )
            return service

        app.dependency_overrides[get_studio_application_service] = _seed_artifact
        try:
            listed = client.get(f"/api/v3/studio/episodes/{episode_id}/artifacts")
            assert listed.status_code == 200
            items = listed.json()["items"]
            assert len(items) == 1
            assert items[0]["artifact_type"] == "IdeaCandidateSet"
            assert items[0]["content_hash"] == HASH
            assert items[0]["artifact_url"].endswith("artifact_0001")

            detail = client.get("/api/v3/studio/artifacts/artifact_0001")
            assert detail.status_code == 200
            assert detail.json()["content"]["candidates"][0]["id"] == "candidate_rabbit_kite"

            missing = client.get("/api/v3/studio/artifacts/artifact_9999")
            assert missing.status_code == 404
        finally:
            app.dependency_overrides[get_studio_application_service] = lambda: _build_fake_service()

    # -- V2 regression -----------------------------------------------------

    def test_v2_production_workspace_still_works(self, client):
        res = client.get("/api/v2/video-production/projects/vp_regression_01/workspace")
        assert res.status_code == 200, res.text
        assert res.headers.get("Deprecation") == "true"
        assert res.headers.get("X-WindAgent-V3-Studio") == "/api/v3/studio"
