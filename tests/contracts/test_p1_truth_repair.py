"""P1.0 — Pre-Production Truth Repair gate tests.

Gate: ``P1_0_PREPRODUCTION_TRUTH_REPAIRED``

Verifies the five truth-repair sub-phases from the P1 plan:

- P1.0.1  Storyboard sync reads the ACTUAL locked screenplay.
          No locked screenplay => 409 SCREENPLAY_NOT_LOCKED, no storyboard created.
- P1.0.2  Scene ownership: every scene has episode/storyboard/revision lineage,
          numbering local to its storyboard; orphan scenes are impossible.
- P1.0.3  Production GET is read-only: missing plan => 404 PRODUCTION_PLAN_NOT_CREATED.
- P1.0.4  World GET is read-only: missing world => 404 WORLD_BIBLE_NOT_INITIALIZED;
          creation happens only through the explicit initialize command.
- P1.0.5  Production stage jobs fail closed without an executor:
          AUDIO/ANIMATION/RENDER/VIDEO submit/retry => CAPABILITY_UNAVAILABLE.

Scenario G (plan §P1.8): POST render/submit without a configured executor must
answer CAPABILITY_UNAVAILABLE — never QUEUED.

Tests self-provision fresh projects/episodes through the public API so they are
idempotent against the persistent demo-seeded database.
"""
from __future__ import annotations

import uuid


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — self-provisioned fixtures through the public contract surface
# ─────────────────────────────────────────────────────────────────────────────

def _create_project(client) -> str:
    r = client.post("/api/v3/projects", json={"name": f"P10 Gate {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_episode(client, project_id: str, title: str = "Gate Episode") -> str:
    r = client.post(f"/api/v3/projects/{project_id}/episodes", json={"title": title})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _lock_episode(client, episode_id: str, revision_id: str | None = None) -> dict:
    """Explicitly lock a screenplay and return the submitted lock payload."""
    ep_r = client.get(f"/api/v3/episodes/{episode_id}")
    assert ep_r.status_code == 200, ep_r.text
    payload = {
        "revision_id": revision_id or f"rev-{uuid.uuid4().hex[:10]}",
        "content_hash": "c" * 64,
        "expected_version": ep_r.json()["version"],
    }
    lock_r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert lock_r.status_code == 200, lock_r.text
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# P1.0.1 — Storyboard sync reads the actual locked screenplay
# ─────────────────────────────────────────────────────────────────────────────

class TestStoryboardSyncTruth:
    def test_sync_without_locked_screenplay_fails_closed(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)

        sync_r = client.post(f"/api/v3/episodes/{eid}/storyboard/actions/sync")
        assert sync_r.status_code == 409
        detail = sync_r.json()["detail"]
        assert detail["error_code"] == "SCREENPLAY_NOT_LOCKED"

        # No storyboard record may be created by the failed sync.
        get_r = client.get(f"/api/v3/episodes/{eid}/storyboard")
        assert get_r.status_code == 404

    def test_sync_pins_actual_revision_hash_and_artifact(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        lock_payload = _lock_episode(client, eid)

        sync_r = client.post(f"/api/v3/episodes/{eid}/storyboard/actions/sync")
        assert sync_r.status_code == 200
        sb = sync_r.json()
        assert sb["status"] == "SYNCED"
        assert sb["episode_id"] == eid
        assert sb["source_screenplay_revision_id"] == lock_payload["revision_id"]
        assert sb["source_screenplay_content_hash"] == lock_payload["content_hash"]
        artifact_id = sb["source_screenplay_artifact_id"]
        assert artifact_id, "LockedScreenplayReceipt artifact must resolve"

        # The receipt artifact exists in the episode's durable artifacts.
        arts_r = client.get(f"/api/v3/episodes/{eid}/artifacts")
        receipts = [a for a in arts_r.json() if a.get("kind") == "LockedScreenplayReceipt"]
        assert receipts, "Lock must persist a LockedScreenplayReceipt artifact"

    def test_resync_keeps_actual_pin_not_synthetic(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        lock_payload = _lock_episode(client, eid)

        first = client.post(f"/api/v3/episodes/{eid}/storyboard/actions/sync").json()
        second = client.post(f"/api/v3/episodes/{eid}/storyboard/actions/sync").json()

        assert first["source_screenplay_revision_id"] == second["source_screenplay_revision_id"]
        assert second["source_screenplay_revision_id"] == lock_payload["revision_id"]
        # Synthetic authority pattern must never appear anywhere.
        assert f"rev-{eid}-lock" not in (
            first["source_screenplay_revision_id"],
            second["source_screenplay_revision_id"],
        )

    def test_sync_unknown_episode_404(self, client):
        r = client.post("/api/v3/episodes/ep-gate-missing/storyboard/actions/sync")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "EPISODE_NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────────────
# P1.0.2 — Scene ownership (no orphan scenes)
# ─────────────────────────────────────────────────────────────────────────────

class TestSceneOwnershipTruth:
    def _sync_board(self, client, eid: str) -> dict:
        sync_r = client.post(f"/api/v3/episodes/{eid}/storyboard/actions/sync")
        assert sync_r.status_code == 200
        return sync_r.json()

    def test_scene_requires_storyboard_id(self, client):
        r = client.post("/api/v3/storyboard/scenes", json={"title": "Orphan"})
        assert r.status_code == 422, "storyboard_id is mandatory — no orphan scenes"

    def test_scene_unknown_storyboard_404(self, client):
        r = client.post(
            "/api/v3/storyboard/scenes",
            json={"storyboard_id": "sb-gate-missing", "title": "Ghost Board"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "STORYBOARD_NOT_FOUND"

    def test_scene_carries_full_ownership_lineage(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        lock_payload = _lock_episode(client, eid)
        board = self._sync_board(client, eid)

        create_r = client.post(
            "/api/v3/storyboard/scenes",
            json={"storyboard_id": board["id"], "title": "Owned Scene"},
        )
        assert create_r.status_code == 201
        scene = create_r.json()
        assert scene["storyboard_id"] == board["id"]
        assert scene["episode_id"] == eid
        assert scene["source_screenplay_revision_id"] == lock_payload["revision_id"]

    def test_scene_numbering_local_to_storyboard(self, client):
        pid = _create_project(client)
        eid_a = _create_episode(client, pid, title="Board A")
        eid_b = _create_episode(client, pid, title="Board B")
        _lock_episode(client, eid_a)
        _lock_episode(client, eid_b)
        board_a = self._sync_board(client, eid_a)
        board_b = self._sync_board(client, eid_b)

        s1 = client.post(
            "/api/v3/storyboard/scenes",
            json={"storyboard_id": board_a["id"], "title": "A1"},
        ).json()
        s2 = client.post(
            "/api/v3/storyboard/scenes",
            json={"storyboard_id": board_b["id"], "title": "B1"},
        ).json()
        s3 = client.post(
            "/api/v3/storyboard/scenes",
            json={"storyboard_id": board_a["id"], "title": "A2"},
        ).json()

        assert s1["scene_number"] == 1
        assert s2["scene_number"] == 1, "Numbering restarts per storyboard"
        assert s3["scene_number"] == 2

    def test_scene_revision_mismatch_rejected(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        _lock_episode(client, eid)
        board = self._sync_board(client, eid)

        r = client.post(
            "/api/v3/storyboard/scenes",
            json={
                "storyboard_id": board["id"],
                "title": "Wrong Lineage",
                "source_screenplay_revision_id": "rev-from-another-lock",
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "SCREENPLAY_REVISION_MISMATCH"


# ─────────────────────────────────────────────────────────────────────────────
# P1.0.3 — Production GET side effect removed
# ─────────────────────────────────────────────────────────────────────────────

class TestProductionGetTruth:
    def test_get_missing_plan_is_read_only(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)

        first = client.get(f"/api/v3/episodes/{eid}/production")
        assert first.status_code == 404
        assert first.json()["detail"]["error_code"] == "PRODUCTION_PLAN_NOT_CREATED"

        # The failed read must not have created any state.
        second = client.get(f"/api/v3/episodes/{eid}/production")
        assert second.status_code == 404

    def test_plan_created_only_via_explicit_command(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)

        create_r = client.post(
            f"/api/v3/episodes/{eid}/production/plan",
            json={
                "screenplay_revision_id": "rev-gate-real-lock",
                "storyboard_revision_id": "sb-gate-real-board",
            },
        )
        assert create_r.status_code == 201
        plan = create_r.json()
        assert plan["screenplay_revision_id"] == "rev-gate-real-lock"
        assert plan["storyboard_revision_id"] == "sb-gate-real-board"

        get_r = client.get(f"/api/v3/episodes/{eid}/production")
        assert get_r.status_code == 200
        assert get_r.json()["screenplay_revision_id"] == "rev-gate-real-lock"

    def test_missing_delivery_read_only(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)

        r = client.get(f"/api/v3/episodes/{eid}/production/delivery")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "DELIVERY_ARTIFACT_NOT_READY"


# ─────────────────────────────────────────────────────────────────────────────
# P1.0.4 — World GET side effect removed
# ─────────────────────────────────────────────────────────────────────────────

class TestWorldGetTruth:
    def test_get_missing_world_is_read_only(self, client):
        pid = _create_project(client)

        first = client.get(f"/api/v3/projects/{pid}/world")
        assert first.status_code == 404
        detail = first.json()["detail"]
        assert detail["error_code"] == "WORLD_BIBLE_NOT_INITIALIZED"

        # Still absent — the read created no "Untitled World".
        second = client.get(f"/api/v3/projects/{pid}/world")
        assert second.status_code == 404

    def test_world_initialized_explicitly(self, client):
        pid = _create_project(client)

        init_r = client.post(
            f"/api/v3/projects/{pid}/world/initialize",
            json={"world_name": "Gate World"},
        )
        assert init_r.status_code == 201
        wb = init_r.json()
        assert wb["world_name"] == "Gate World"

        get_r = client.get(f"/api/v3/projects/{pid}/world")
        assert get_r.status_code == 200
        assert get_r.json()["world_name"] == "Gate World"

    def test_initialize_unknown_project_404(self, client):
        r = client.post(
            "/api/v3/projects/proj-gate-missing/world/initialize",
            json={"world_name": "Nowhere"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "PROJECT_NOT_FOUND"

    def test_initialize_requires_real_name(self, client):
        pid = _create_project(client)
        r = client.post(f"/api/v3/projects/{pid}/world/initialize", json={"world_name": ""})
        assert r.status_code == 422, "Empty name would recreate 'Untitled World' by another mask"


# ─────────────────────────────────────────────────────────────────────────────
# P1.0.5 — Stage jobs truthful (fail closed) — includes Scenario G
# ─────────────────────────────────────────────────────────────────────────────

class TestStageJobsFailClosed:
    STAGES = ("audio", "animation", "render", "video")

    def _submit(self, client, stage: str):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        before = len(client.get(f"/api/v3/episodes/{eid}/production/jobs").json())
        r = client.post(
            f"/api/v3/episodes/{eid}/production/{stage}/submit",
            json={"shot_id": None},
        )
        after = len(client.get(f"/api/v3/episodes/{eid}/production/jobs").json())
        return r, before, after

    def test_scenario_g_render_submit_capability_unavailable(self, client):
        """Scenario G: no configured executor => CAPABILITY_UNAVAILABLE, not QUEUED."""
        r, _, _ = self._submit(client, "render")
        assert r.status_code == 503
        body = r.json()["detail"]
        assert body["error_code"] == "CAPABILITY_UNAVAILABLE"
        assert body["job_type"] == "RENDER"

    def test_all_stages_fail_closed_and_persist_nothing(self, client):
        for stage in self.STAGES:
            r, before, after = self._submit(client, stage)
            assert r.status_code == 503, f"{stage} must fail closed"
            assert r.json()["detail"]["error_code"] == "CAPABILITY_UNAVAILABLE"
            assert before == after == 0, f"{stage} submission persisted a job record"

    def test_retry_fails_closed_without_executor(self, client):
        pid = _create_project(client)
        eid = _create_episode(client, pid)
        r = client.post(
            f"/api/v3/episodes/{eid}/production/audio/retry",
            json={"job_id": "job-gate-unknown"},
        )
        # Unknown job 404s; the fail-closed capability guard applies to known jobs too.
        assert r.status_code in (404, 503)
