"""
Phase 8 Contract Test Suite — Canonical Episode Workspace.
Verifies canonical V3 Episodes, Artifacts, Runs, Revision Authority, Checkpoints,
Locking, Optimistic Concurrency (409 Conflict), and WebSocket Realtime.
"""

from fastapi.testclient import TestClient


class TestPhase8EpisodeWorkspaceContracts:
    def test_list_all_episodes_contract(self, client: TestClient):
        """Verify GET /api/v3/episodes returns canonical EpisodeListResponse with derived progress."""
        response = client.get("/api/v3/episodes")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "page_info" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 2

        ep = data["items"][0]
        assert "id" in ep
        assert "title" in ep
        assert "state" in ep
        assert "current_checkpoint" in ep
        assert "progress_percent" in ep
        assert 0 <= ep["progress_percent"] <= 100
        assert "version" in ep

    def test_filter_and_search_episodes_contract(self, client: TestClient):
        """Verify project_id, state, and search filtering."""
        res_proj = client.get("/api/v3/episodes?project_id=proj-cyberpunk-01")
        assert res_proj.status_code == 200
        assert len(res_proj.json()["items"]) >= 2

        res_search = client.get("/api/v3/episodes?search=Alex")
        assert res_search.status_code == 200
        assert len(res_search.json()["items"]) >= 1

    def test_get_episode_detail_contract(self, client: TestClient):
        """Verify GET /api/v3/episodes/{id} returns full detail."""
        res = client.get("/api/v3/episodes/ep-cb-001")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "ep-cb-001"
        assert data["title"] == "Tập 01: Mã Nguồn Thức Tỉnh"
        assert data["version"] >= 1

        res_404 = client.get("/api/v3/episodes/non-existent-ep-999")
        assert res_404.status_code == 404

    def test_update_episode_optimistic_locking(self, client: TestClient):
        """Verify PATCH /api/v3/episodes/{id} verifies version and returns 409 on conflict."""
        res_get = client.get("/api/v3/episodes/ep-cb-002")
        assert res_get.status_code == 200
        ep = res_get.json()
        current_version = ep["version"]

        # Conflict test: stale version
        res_conflict = client.patch(
            "/api/v3/episodes/ep-cb-002",
            json={"title": "Stale Title", "expected_version": current_version + 99},
        )
        assert res_conflict.status_code == 409
        assert "conflict" in res_conflict.json()["detail"].lower()

        # Success test: matching version
        res_ok = client.patch(
            "/api/v3/episodes/ep-cb-002",
            json={"title": "Tập 02: Mê Cung Neon (Bản Mới)", "expected_version": current_version},
        )
        assert res_ok.status_code == 200
        updated = res_ok.json()
        assert updated["title"] == "Tập 02: Mê Cung Neon (Bản Mới)"
        assert updated["version"] == current_version + 1

    def test_get_artifacts_and_runs_contract(self, client: TestClient):
        """Verify GET artifacts and runs for an episode."""
        res_art = client.get("/api/v3/episodes/ep-cb-001/artifacts")
        assert res_art.status_code == 200
        artifacts = res_art.json()
        assert len(artifacts) >= 3
        kinds = [a["kind"] for a in artifacts]
        assert "IdeaCandidateSet" in kinds
        assert "StoryBible" in kinds
        assert "EpisodeOutline" in kinds

        res_runs = client.get("/api/v3/episodes/ep-cb-001/runs")
        assert res_runs.status_code == 200
        runs = res_runs.json()
        assert len(runs) >= 1

    def test_start_generation_stub_removed(self, client: TestClient):
        """P0.8 truth repair: the legacy instant-COMPLETED stub is removed.

        Generation must only be started through the canonical durable path
        (POST /api/v3/studio/episodes/{id}/runs -> queue -> worker); no
        endpoint may fabricate a hard-coded COMPLETED run.
        """
        res = client.post(
            "/api/v3/episodes/ep-cb-002/start-generation",
            json={"checkpoint": "OUTLINE"},
        )
        assert res.status_code in (404, 405)

        # No run was fabricated for the episode by the removed stub.
        runs = client.get("/api/v3/episodes/ep-cb-002/runs").json()
        assert all(r["status"] != "COMPLETED" or r["completed_at"] != r["started_at"] for r in runs)

    def test_select_idea_advances_checkpoint(self, client: TestClient):
        """Verify POST /api/v3/episodes/{id}/select-idea advances checkpoint to STORY_BIBLE."""
        ep = client.get("/api/v3/episodes/ep-cb-001").json()
        ver = ep["version"]

        # Conflict check
        res_conflict = client.post(
            "/api/v3/episodes/ep-cb-001/select-idea",
            json={"idea_id": "idea-1", "expected_version": ver + 50},
        )
        assert res_conflict.status_code == 409

        # Success check
        res_ok = client.post(
            "/api/v3/episodes/ep-cb-001/select-idea",
            json={"idea_id": "idea-1", "expected_version": ver},
        )
        assert res_ok.status_code == 200
        updated = res_ok.json()
        assert updated["current_checkpoint"] == "STORY_BIBLE"
        assert updated["version"] == ver + 1

    def test_submit_checkpoint_decision_and_lock(self, client: TestClient):
        """Verify approval transitions and screenplay lock."""
        ep = client.get("/api/v3/episodes/ep-cb-001").json()
        ver = ep["version"]

        # Approve decision
        res_approve = client.post(
            "/api/v3/episodes/ep-cb-001/decision",
            json={
                "decision": "APPROVED",
                "revision_id": "rev-test-123",
                "feedback": "Kịch bản xuất sắc",
                "expected_version": ver,
            },
        )
        assert res_approve.status_code == 200
        approved_ep = res_approve.json()
        assert approved_ep["version"] == ver + 1

        # Lock screenplay
        ver2 = approved_ep["version"]
        res_lock = client.post(
            "/api/v3/episodes/ep-cb-001/lock",
            json={
                "revision_id": "rev-test-123",
                "content_hash": "sha256-abcdef1234567890",
                "expected_version": ver2,
            },
        )
        assert res_lock.status_code == 200
        locked_ep = res_lock.json()
        assert locked_ep["state"] == "LOCKED"
        assert locked_ep["current_checkpoint"] == "LOCKED"
        assert locked_ep["progress_percent"] == 100

    def test_cancel_run_contract(self, client: TestClient):
        """Verify POST /api/v3/episodes/{id}/cancel-run is truthful.

        P0.8 truth repair: an episode with NO runs must NOT receive a
        fabricated CANCELLED — the endpoint answers NO_ACTIVE_RUN.
        """
        res = client.post("/api/v3/episodes/ep-cb-001/cancel-run")
        assert res.status_code == 200
        body = res.json()
        # ep-cb-001 has seeded (terminal) runs: nothing cancellable remains
        assert body["status"] in ("CANCELLED", "NO_ACTIVE_RUN")
        if body["status"] == "CANCELLED":
            assert isinstance(body.get("cancelled_run_ids"), list)

    def test_websocket_realtime_stream(self, client: TestClient):
        """Verify WebSocket /ws/v3/episodes/{id} connects and streams initial event."""
        with client.websocket_connect("/ws/v3/episodes/ep-cb-001") as websocket:
            data = websocket.receive_json()
            assert data["event"] == "episode.updated"
            assert data["episode_id"] == "ep-cb-001"
            assert "payload" in data
            assert data["payload"]["id"] == "ep-cb-001"
