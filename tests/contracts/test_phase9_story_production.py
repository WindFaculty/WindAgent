"""
Phase 9F — Integration Certification: Story Production Domain Contract Tests.
Verifies cross-domain integrity:
- Character references valid in storyboard scenes (by ID, not free text)
- World/Location references valid
- Screenplay revision pinned in storyboard scenes (source_screenplay_revision_id)
- Asset provenance valid (required fields present, content_hash non-empty)
- Review decisions pinned to revision_id + expected_version
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9A — Characters
# ─────────────────────────────────────────────────────────────────────────────

class TestCharactersE2E:
    def test_list_characters_returns_no_defaults(self, client):
        """Character list comes from backend, not DEFAULT_CHARACTERS hardcode."""
        r = client.get("/api/v3/projects/proj-cyberpunk-01/characters")
        assert r.status_code == 200
        chars = r.json()
        assert isinstance(chars, list)
        # Characters have canonical identity/psychology/visual_profile/voice_profile
        for char in chars:
            assert "identity" in char, "Character must have canonical identity block"
            assert "psychology" in char
            assert "visual_profile" in char
            assert "voice_profile" in char
            assert "relationships" in char

    def test_create_character_idempotent(self, client):
        key = "test-idem-char-9f-001"
        payload = {"name": "Test Character 9F", "role": "Supporting", "biography": "Test bio"}
        r1 = client.post("/api/v3/projects/proj-cyberpunk-01/characters", json=payload, headers={"Idempotency-Key": key})
        r2 = client.post("/api/v3/projects/proj-cyberpunk-01/characters", json=payload, headers={"Idempotency-Key": key})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"], "Idempotency must return same character"

    def test_update_character_optimistic_lock(self, client):
        """PATCH must reject stale expected_version."""
        r = client.get("/api/v3/projects/proj-cyberpunk-01/characters")
        char = r.json()[0]
        stale_version = char["version"] - 1 if char["version"] > 1 else 999

        r_conflict = client.patch(
            f"/api/v3/characters/{char['id']}",
            json={"name": "Should Fail", "expected_version": stale_version},
        )
        assert r_conflict.status_code == 409, "Stale version must yield 409 Conflict"

    def test_character_relationships_use_ids(self, client):
        """Relationships must reference target_character_id (UUID), not free-text name."""
        r = client.get("/api/v3/characters/char-kaelen-01/relationships")
        assert r.status_code == 200
        for rel in r.json():
            assert "target_character_id" in rel, "Relationship must use character ID"
            assert rel["target_character_id"].startswith("char-"), "Character IDs must be stable"

    def test_delete_character(self, client):
        create_r = client.post("/api/v3/projects/proj-cyberpunk-01/characters", json={"name": "ToDelete"})
        char_id = create_r.json()["id"]
        del_r = client.delete(f"/api/v3/characters/{char_id}")
        assert del_r.status_code == 204
        get_r = client.get(f"/api/v3/characters/{char_id}")
        assert get_r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9B — World Bible
# ─────────────────────────────────────────────────────────────────────────────

class TestWorldE2E:
    def test_get_world_bible(self, client):
        r = client.get("/api/v3/projects/proj-cyberpunk-01/world")
        assert r.status_code == 200
        wb = r.json()
        assert "world_name" in wb
        assert "rules" in wb
        assert "locations_count" in wb
        assert "factions_count" in wb
        assert "lore_count" in wb

    def test_update_world_bible_optimistic_lock(self, client):
        wb = client.get("/api/v3/projects/proj-cyberpunk-01/world").json()
        r = client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"core_theme": "Updated theme", "expected_version": wb["version"]},
        )
        assert r.status_code == 200
        assert r.json()["version"] == wb["version"] + 1

    def test_update_world_bible_conflict(self, client):
        r = client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"core_theme": "Conflict", "expected_version": 0},
        )
        assert r.status_code == 409

    def test_list_locations(self, client):
        r = client.get("/api/v3/projects/proj-cyberpunk-01/world/locations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_location(self, client):
        r = client.post(
            "/api/v3/projects/proj-cyberpunk-01/world/locations",
            json={"name": "Test Location 9F", "type": "Interior", "description": "Test"},
        )
        assert r.status_code == 201
        loc = r.json()
        assert loc["id"].startswith("loc-")
        assert loc["name"] == "Test Location 9F"

    def test_list_factions_and_create(self, client):
        r = client.get("/api/v3/projects/proj-cyberpunk-01/world/factions")
        assert r.status_code == 200
        r2 = client.post(
            "/api/v3/projects/proj-cyberpunk-01/world/factions",
            json={"name": "New Faction 9F", "ideology": "test", "influence_level": 50},
        )
        assert r2.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9C — Storyboard
# ─────────────────────────────────────────────────────────────────────────────

class TestStoryboardE2E:
    def test_get_storyboard_pinned_to_revision(self, client):
        r = client.get("/api/v3/episodes/ep-cb-001/storyboard")
        assert r.status_code == 200
        sb = r.json()
        assert "source_screenplay_revision_id" in sb
        assert sb["source_screenplay_revision_id"], "Storyboard must pin a screenplay revision"

    def test_scenes_carry_revision_pin(self, client):
        """Every scene must record source_screenplay_revision_id."""
        r = client.get("/api/v3/episodes/ep-cb-001/storyboard/scenes")
        assert r.status_code == 200
        scenes = r.json()
        assert len(scenes) > 0
        for scene in scenes:
            assert "source_screenplay_revision_id" in scene, \
                f"Scene {scene['id']} must carry source_screenplay_revision_id"
            assert scene["source_screenplay_revision_id"], \
                f"Scene {scene['id']} must have non-null screenplay revision pin"

    def test_trigger_generation_returns_job_id(self, client):
        """Generation must return a server-issued generation_id immediately. No fake timers."""
        r = client.post(
            "/api/v3/storyboard/scenes/scene-cb-001-01/generations",
            json={},
        )
        assert r.status_code == 201
        job = r.json()
        assert "generation_id" in job, "Must return server-issued generation_id"
        assert "submitted_at" in job
        assert job["status"] == "QUEUED", "Initial status must be QUEUED, not a mock terminal state"

    def test_generation_job_polling(self, client):
        """Generation job must be pollable via GET."""
        trigger_r = client.post("/api/v3/storyboard/scenes/scene-cb-001-02/generations", json={})
        gen_id = trigger_r.json()["generation_id"]
        poll_r = client.get(f"/api/v3/storyboard/scenes/scene-cb-001-02/generations/{gen_id}")
        assert poll_r.status_code == 200
        assert poll_r.json()["generation_id"] == gen_id

    def test_update_scene_optimistic_lock(self, client):
        scene_r = client.get("/api/v3/episodes/ep-cb-001/storyboard/scenes")
        scene = scene_r.json()[0]
        r = client.patch(
            f"/api/v3/storyboard/scenes/{scene['id']}",
            json={"title": "Updated Title 9F", "expected_version": scene["version"]},
        )
        assert r.status_code == 200
        conflict_r = client.patch(
            f"/api/v3/storyboard/scenes/{scene['id']}",
            json={"title": "Conflict", "expected_version": scene["version"]},
        )
        assert conflict_r.status_code == 409

    def test_sync_storyboard_action(self, client):
        r = client.post("/api/v3/episodes/ep-cb-001/storyboard/actions/sync")
        assert r.status_code == 200
        sb = r.json()
        assert sb["status"] == "SYNCED"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9D — Reviews
# ─────────────────────────────────────────────────────────────────────────────

class TestReviewsE2E:
    def test_list_reviews_no_defaults(self, client):
        r = client.get("/api/v3/reviews")
        assert r.status_code == 200
        reviews = r.json()
        assert isinstance(reviews, list)
        for rev in reviews:
            assert "subject_type" in rev
            assert "subject_id" in rev
            assert "status" in rev

    def test_create_review_and_add_comment(self, client):
        r = client.post("/api/v3/reviews", json={
            "subject_type": "character_revision",
            "subject_id": "char-kaelen-01",
            "project_id": "proj-cyberpunk-01",
        })
        assert r.status_code == 201
        review_id = r.json()["id"]

        cmt_r = client.post(f"/api/v3/reviews/{review_id}/comments", json={
            "author": "Director Agent",
            "role": "Director Agent",
            "text": "Nhân vật cần cập nhật tiểu sử chi tiết hơn.",
        })
        assert cmt_r.status_code == 201
        assert cmt_r.json()["text"]

    def test_decision_pinned_to_revision(self, client):
        """Decision must include revision_id + expected_version."""
        r = client.post("/api/v3/reviews", json={
            "subject_type": "asset_revision",
            "subject_id": "asset-concept-cb-001-01",
        })
        review_id = r.json()["id"]

        dec_r = client.post(f"/api/v3/reviews/{review_id}/decision", json={
            "decision": "APPROVED",
            "revision_id": "rev-asset-001-v1",
            "expected_version": 1,
            "reason": "Asset đạt yêu cầu chất lượng.",
            "decided_by": "Producer Agent",
        })
        assert dec_r.status_code == 200
        decision = dec_r.json()
        assert decision["revision_id"] == "rev-asset-001-v1"
        assert decision["expected_version"] == 1
        assert decision["decision"] == "APPROVED"

    def test_duplicate_terminal_decision_rejected(self, client):
        """Cannot submit a second terminal decision on an already-approved review."""
        r = client.get("/api/v3/reviews?status=APPROVED")
        if not r.json():
            pytest.skip("No approved reviews to test duplicate decision")
        review_id = r.json()[0]["id"]
        dec_r = client.post(f"/api/v3/reviews/{review_id}/decision", json={
            "decision": "APPROVED",
            "revision_id": "rev-x",
            "expected_version": 1,
            "decided_by": "Tester",
        })
        assert dec_r.status_code == 409, "Duplicate terminal decision must return 409"

    def test_invalid_subject_type_rejected(self, client):
        r = client.post("/api/v3/reviews", json={"subject_type": "INVALID_TYPE", "subject_id": "x"})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9E — Assets
# ─────────────────────────────────────────────────────────────────────────────

class TestAssetsE2E:
    def test_create_asset_has_provenance(self, client):
        """Every asset must record provenance chain at creation time."""
        r = client.post("/api/v3/assets", json={
            "name": "Test Concept Art 9F",
            "type": "IMAGE",
            "episode_id": "ep-cb-001",
            "source": "GENERATED",
            "generator": "Imagen",
            "model": "imagen-3.5-generate",
            "prompt": "Test prompt for phase 9F certification",
        })
        assert r.status_code == 201
        asset = r.json()
        prov = asset["provenance"]
        assert prov["source"] == "GENERATED"
        assert prov["generator"] == "Imagen"
        assert prov["model"] == "imagen-3.5-generate"
        assert prov["content_hash"], "content_hash must not be empty"

    def test_asset_revisions_history(self, client):
        """Must be able to retrieve revision history."""
        r = client.get("/api/v3/assets/asset-concept-cb-001-01/revisions")
        assert r.status_code == 200
        revisions = r.json()
        assert len(revisions) >= 1
        for rev in revisions:
            assert "revision_id" in rev
            assert "version" in rev
            assert "provenance" in rev
            assert rev["provenance"]["content_hash"], "Revision must have content_hash"

    def test_asset_provenance_endpoint(self, client):
        r = client.get("/api/v3/assets/asset-concept-cb-001-01/provenance")
        assert r.status_code == 200
        prov = r.json()
        assert "source" in prov
        assert "content_hash" in prov
        assert prov["content_hash"], "content_hash must be non-empty"

    def test_asset_approve_pinned_to_revision(self, client):
        """Approve must reference a specific revision_id."""
        r = client.post("/api/v3/assets", json={"name": "Approve Test 9F", "source": "GENERATED"})
        asset_id = r.json()["id"]
        revs = client.get(f"/api/v3/assets/{asset_id}/revisions").json()
        rev_id = revs[0]["revision_id"]

        approve_r = client.post(f"/api/v3/assets/{asset_id}/actions/approve", json={
            "revision_id": rev_id,
            "reason": "Chất lượng đạt yêu cầu.",
            "approved_by": "Producer Agent",
        })
        assert approve_r.status_code == 200
        assert approve_r.json()["status"] == "APPROVED"

    def test_asset_reject_pinned_to_revision(self, client):
        r = client.post("/api/v3/assets", json={"name": "Reject Test 9F", "source": "UPLOADED"})
        asset_id = r.json()["id"]
        revs = client.get(f"/api/v3/assets/{asset_id}/revisions").json()
        rev_id = revs[0]["revision_id"]

        reject_r = client.post(f"/api/v3/assets/{asset_id}/actions/reject", json={
            "revision_id": rev_id,
            "reason": "Không đạt tiêu chuẩn màu sắc.",
            "rejected_by": "Director Agent",
        })
        assert reject_r.status_code == 200
        assert reject_r.json()["status"] == "REJECTED"

    def test_approve_nonexistent_revision_rejected(self, client):
        r = client.post("/api/v3/assets/asset-concept-cb-001-01/actions/approve", json={
            "revision_id": "rev-does-not-exist",
            "approved_by": "Tester",
        })
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9F — Cross-Domain Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainIntegration:
    def test_character_ids_in_scenes_are_valid(self, client):
        """Scene character_ids must reference valid character IDs in the same project."""
        chars_r = client.get("/api/v3/projects/proj-cyberpunk-01/characters")
        valid_char_ids = {c["id"] for c in chars_r.json()}

        scenes_r = client.get("/api/v3/episodes/ep-cb-001/storyboard/scenes")
        for scene in scenes_r.json():
            for cid in scene.get("character_ids", []):
                assert cid in valid_char_ids, \
                    f"Scene {scene['id']} references invalid character_id: {cid}"

    def test_storyboard_revision_consistent_with_episode(self, client):
        """Storyboard revision must be consistent across storyboard header and scenes."""
        sb = client.get("/api/v3/episodes/ep-cb-001/storyboard").json()
        board_rev_id = sb["source_screenplay_revision_id"]

        scenes = client.get("/api/v3/episodes/ep-cb-001/storyboard/scenes").json()
        for scene in scenes:
            scene_rev_id = scene.get("source_screenplay_revision_id")
            if scene_rev_id:
                assert scene_rev_id == board_rev_id, \
                    f"Scene {scene['id']} pinned to {scene_rev_id}, expected {board_rev_id}"

    def test_asset_job_id_traceable(self, client):
        """Assets produced by generation jobs should reference job_id for traceability."""
        gen_r = client.post("/api/v3/storyboard/scenes/scene-cb-001-01/generations", json={})
        job_id = gen_r.json()["generation_id"]

        asset_r = client.post("/api/v3/assets", json={
            "name": "Generated Concept 9F",
            "type": "IMAGE",
            "source": "GENERATED",
            "generator": "Imagen",
            "model": "imagen-3.5-generate",
            "job_id": job_id,
            "episode_id": "ep-cb-001",
            "scene_id": "scene-cb-001-01",
        })
        assert asset_r.status_code == 201
        assert asset_r.json()["provenance"]["job_id"] == job_id

    def test_review_decision_revision_schema(self, client):
        """Review decisions must always carry revision_id + expected_version (cannot approve mutable objects)."""
        r = client.post("/api/v3/reviews", json={"subject_type": "storyboard", "subject_id": "sb-cb-001"})
        review_id = r.json()["id"]

        # Submit without revision_id — must fail
        bad_r = client.post(f"/api/v3/reviews/{review_id}/decision", json={
            "decision": "APPROVED",
            "revision_id": "",
            "expected_version": 1,
            "decided_by": "Tester",
        })
        assert bad_r.status_code in (422, 400), "Must reject decision with empty revision_id"
