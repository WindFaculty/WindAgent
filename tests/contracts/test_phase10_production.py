"""
Phase 10 — Production Cutover Domain Contract Tests.
Verifies:
- Episode -> Production plan lifecycle & pinned screenplay/storyboard revisions
- GET is read-only (P1.0: no plan auto-creation, no synthetic revision pins)
- Shot CRUD & optimistic concurrency (version locking)
- Stage jobs (Audio, Animation, Render, Video) fail closed with
  CAPABILITY_UNAVAILABLE until real executors are composed in P2
- Job cancellation on existing records & fail-closed retry
- Truthful failure diagnostics (error codes, retryable flag, stage)
- Delivery artifact resolution without read-side effects
- Cross-domain integration
"""
from __future__ import annotations



# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.1 — Production Plan
# ─────────────────────────────────────────────────────────────────────────────

class TestProductionPlan:
    def test_get_existing_production_plan(self, client):
        r = client.get("/api/v3/episodes/ep-cb-001/production")
        assert r.status_code == 200
        plan = r.json()
        assert plan["episode_id"] == "ep-cb-001"
        assert "screenplay_revision_id" in plan
        assert "storyboard_revision_id" in plan
        assert "status" in plan
        assert "progress_percent" in plan
        assert "version" in plan

    def test_get_missing_production_plan_does_not_create(self, client):
        """P1.0 truth repair: GET is read-only — no synthetic plan, no fake pins."""
        r = client.get("/api/v3/episodes/ep-p10-uninitialized/production")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "PRODUCTION_PLAN_NOT_CREATED"

        # No record was created by the failed read.
        r2 = client.get("/api/v3/episodes/ep-p10-uninitialized/production")
        assert r2.status_code == 404

    def test_create_production_plan_pinned_revisions(self, client):
        payload = {
            "screenplay_revision_id": "rev-test-screen-lock",
            "storyboard_revision_id": "sb-test-lock",
            "character_references": ["char-kaelen-01"],
            "asset_references": ["asset-concept-cb-001-01"],
        }
        r = client.post("/api/v3/episodes/ep-test-p10/production/plan", json=payload)
        assert r.status_code == 201
        plan = r.json()
        assert plan["screenplay_revision_id"] == "rev-test-screen-lock"
        assert plan["storyboard_revision_id"] == "sb-test-lock"
        assert "char-kaelen-01" in plan["character_references"]

    def test_plan_requires_pinned_revisions(self, client):
        payload = {
            "screenplay_revision_id": "",
            "storyboard_revision_id": "sb-test",
        }
        r = client.post("/api/v3/episodes/ep-test-p10/production/plan", json=payload)
        assert r.status_code in (422, 400)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.2 — Shots
# ─────────────────────────────────────────────────────────────────────────────

class TestShots:
    def test_list_shots_ordered(self, client):
        r = client.get("/api/v3/episodes/ep-cb-001/shots")
        assert r.status_code == 200
        shots = r.json()
        assert isinstance(shots, list)
        assert len(shots) >= 3
        # Verify ordering
        for i in range(len(shots) - 1):
            assert shots[i]["shot_number"] <= shots[i + 1]["shot_number"]

    def test_create_shot(self, client):
        payload = {
            "camera_movement": "Crane Shot Up",
            "focal_length": "85mm Prime",
            "duration_seconds": 6,
        }
        r = client.post("/api/v3/episodes/ep-cb-001/shots", json=payload)
        assert r.status_code == 201
        shot = r.json()
        assert shot["id"].startswith("shot-")
        assert shot["camera_movement"] == "Crane Shot Up"
        assert shot["focal_length"] == "85mm Prime"
        assert shot["duration_seconds"] == 6

    def test_get_shot_detail(self, client):
        r = client.get("/api/v3/shots/shot-cb-001-01")
        assert r.status_code == 200
        shot = r.json()
        assert shot["id"] == "shot-cb-001-01"
        assert shot["status"] == "RENDERED"

    def test_update_shot_optimistic_locking(self, client):
        r = client.get("/api/v3/shots/shot-cb-001-02")
        shot = r.json()
        expected_version = shot["version"]

        # Valid update
        patch_r = client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={"camera_movement": "Whip Pan Left", "expected_version": expected_version},
        )
        assert patch_r.status_code == 200
        assert patch_r.json()["camera_movement"] == "Whip Pan Left"
        assert patch_r.json()["version"] == expected_version + 1

        # Conflict on stale version
        conflict_r = client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={"camera_movement": "Should Fail", "expected_version": expected_version},
        )
        assert conflict_r.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.3 — Stage Jobs (Audio, Animation, Render, Video)
# ─────────────────────────────────────────────────────────────────────────────

class TestStageJobs:
    """P1.0 truth repair (P1.0.5): stage jobs fail closed without a real executor.

    AUDIO / ANIMATION / RENDER / VIDEO submissions must return
    CAPABILITY_UNAVAILABLE and persist nothing until P2 wires executors.
    """

    def _assert_capability_unavailable(self, client, stage):
        r = client.post(
            f"/api/v3/episodes/ep-cb-001/production/{stage}/submit",
            json={"shot_id": "shot-cb-001-01", "correlation_id": "test-corr-fail-closed"},
        )
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["error_code"] == "CAPABILITY_UNAVAILABLE"
        assert detail["job_type"] == stage.upper()
        return r

    def test_submit_audio_job_fails_closed(self, client):
        self._assert_capability_unavailable(client, "audio")

    def test_submit_animation_job_fails_closed(self, client):
        self._assert_capability_unavailable(client, "animation")

    def test_submit_render_job_fails_closed(self, client):
        self._assert_capability_unavailable(client, "render")

    def test_submit_video_job_fails_closed(self, client):
        self._assert_capability_unavailable(client, "video")

    def test_failed_submission_persists_no_queued_job(self, client):
        """No fake QUEUED record may survive a failed submission."""
        before = len(client.get("/api/v3/episodes/ep-cb-001/production/jobs").json())
        self._assert_capability_unavailable(client, "render")
        after = len(client.get("/api/v3/episodes/ep-cb-001/production/jobs").json())
        assert after == before, "CAPABILITY_UNAVAILABLE submission must not create job records"

    def test_retry_fails_closed_without_executor(self, client):
        retry_r = client.post(
            "/api/v3/episodes/ep-cb-001/production/audio/retry",
            json={"job_id": "job-audio-001"},
        )
        assert retry_r.status_code == 503
        assert retry_r.json()["detail"]["error_code"] == "CAPABILITY_UNAVAILABLE"

    def test_cancel_existing_job(self, client):
        cancel_r = client.post(
            "/api/v3/episodes/ep-cb-001/production/render/cancel",
            json={"job_id": "job-render-001", "reason": "User stopped execution"},
        )
        assert cancel_r.status_code == 200
        assert cancel_r.json()["state"] == "CANCELLED"

    def test_cancel_unknown_job_404(self, client):
        cancel_r = client.post(
            "/api/v3/episodes/ep-cb-001/production/render/cancel",
            json={"job_id": "job-does-not-exist"},
        )
        assert cancel_r.status_code == 404

    def test_list_jobs_and_filter_by_stage(self, client):
        r = client.get("/api/v3/episodes/ep-cb-001/production/jobs")
        assert r.status_code == 200
        all_jobs = r.json()
        assert isinstance(all_jobs, list)

        r_render = client.get("/api/v3/episodes/ep-cb-001/production/jobs?stage=RENDER")
        assert r_render.status_code == 200
        for j in r_render.json():
            assert j["job_type"] == "RENDER"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.4 — Delivery Package
# ─────────────────────────────────────────────────────────────────────────────

class TestDeliveryPackage:
    def test_get_delivery_artifact(self, client):
        r = client.get("/api/v3/episodes/ep-cb-001/production/delivery")
        assert r.status_code == 200
        delivery = r.json()
        assert delivery["episode_id"] == "ep-cb-001"
        assert "resolution" in delivery
        assert "codec" in delivery
        assert "duration_seconds" in delivery
        assert "file_size_bytes" in delivery

    def test_get_missing_delivery_does_not_create(self, client):
        """P1.0 truth repair: reads never fabricate delivery records."""
        r = client.get("/api/v3/episodes/ep-p10-uninitialized/production/delivery")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "DELIVERY_ARTIFACT_NOT_READY"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.5 — Cross-Domain Integration & Authority
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainIntegration:
    def test_production_plan_pins_real_screenplay_and_storyboard(self, client):
        """Production plan must reference locked screenplay and storyboard revisions."""
        plan_r = client.get("/api/v3/episodes/ep-cb-001/production")
        assert plan_r.status_code == 200
        plan = plan_r.json()

        # Storyboard must exist and match
        sb_r = client.get("/api/v3/episodes/ep-cb-001/storyboard")
        assert sb_r.status_code == 200
        sb = sb_r.json()
        assert plan["storyboard_revision_id"] == sb["id"]
        assert plan["screenplay_revision_id"] == sb["source_screenplay_revision_id"]

    def test_shots_reference_valid_scenes(self, client):
        """Shots in production should reference valid storyboard scenes."""
        scenes_r = client.get("/api/v3/episodes/ep-cb-001/storyboard/scenes")
        assert scenes_r.status_code == 200
        valid_scene_ids = {s["id"] for s in scenes_r.json()}

        shots_r = client.get("/api/v3/episodes/ep-cb-001/shots")
        assert shots_r.status_code == 200
        for shot in shots_r.json():
            if shot.get("scene_id"):
                assert shot["scene_id"] in valid_scene_ids, \
                    f"Shot {shot['id']} references invalid scene_id {shot['scene_id']}"
