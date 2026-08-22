"""P1.1 — Character Canon gate tests.

Gate: ``P1_1_CHARACTER_CANON_LIVE``

Covers the P1.1 plan sub-phases against the real API surface:

- Canonical profile sections: identity (aliases), personality
  (traits/archetype/motivation/goal/fears), visual, voice, continuity.
- Source lineage per character version (plan §P1.1.3).
- Immutable revisions with deterministic content hashes (plan §P1.1.5).
- Canon Sync from the ACTUAL locked screenplay (plan §P1.1.4):
  fail-closed without a lock; NO_CHANGE / ADD_CHARACTER / UPDATE_PROPOSED /
  CONFLICT classification; manual edits are never overwritten silently.
- Readiness ladder DRAFT -> REVIEW_REQUIRED -> APPROVED -> PRODUCTION_READY
  gated on name + story role + visual identity + continuity constraints
  (plan §P1.1.6); voice NOT required.

Tests self-provision through the public API and reuse the demo-seeded
Cyberpunk episode (StoryBible + ScreenplayDraft artifacts) by locking it.
"""
from __future__ import annotations

import uuid


def _lock(client, episode_id: str, project_id: str) -> dict:
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    payload = {
        "revision_id": f"rev-{uuid.uuid4().hex[:10]}",
        "content_hash": "a" * 64,
        "expected_version": ep["version"],
    }
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert r.status_code == 200, r.text
    return payload


def _make_production_ready(client, character_id: str, expected_version: int | None = None) -> dict:
    """Fill the readiness fields and walk the status ladder to PRODUCTION_READY."""
    char = client.get(f"/api/v3/characters/{character_id}").json()
    version = expected_version or char["version"]
    r = client.patch(
        f"/api/v3/characters/{character_id}",
        json={
            "physical_description": "Thanh niên gầy, tóc xù, áo khoác bạc",
            "immutable_features": ["Mắt trái nhân tạo màu hổ phách"],
            "wardrobe_rules": ["Luôn mặc áo khoác phản quang bạc"],
            "expected_version": version,
        },
    )
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    ladder = ("DRAFT", "REVIEW_REQUIRED", "APPROVED", "PRODUCTION_READY")
    for target in ladder[ladder.index(r.json()["status"]) + 1:]:
        r = client.post(
            f"/api/v3/characters/{character_id}/actions/set-status",
            json={"status": target, "expected_version": version},
        )
        assert r.status_code == 200, r.text
        version = r.json()["version"]
    return client.get(f"/api/v3/characters/{character_id}").json()


class TestCanonicalProfile:
    def test_create_carries_full_canon_sections(self, client):
        pid = "proj-cyberpunk-01"
        r = client.post(
            f"/api/v3/projects/{pid}/characters",
            json={
                "name": "Nova",
                "role": "Protagonist",
                "aliases": ["Nova-7"],
                "physical_description": "Cao, tóc bạc, mắt trái nhân tạo",
                "immutable_features": ["Mắt trái nhân tạo"],
                "wardrobe_rules": ["Áo khoác bạc phản quang"],
            },
        )
        assert r.status_code == 201, r.text
        char = r.json()
        assert char["identity"]["name"] == "Nova"
        assert char["identity"]["aliases"] == ["Nova-7"]
        for section in ("identity", "psychology", "visual_profile", "voice_profile", "continuity"):
            assert section in char, f"canonical section '{section}' missing"
        assert char["continuity"]["immutable_features"] == ["Mắt trái nhân tạo"]
        assert char["status"] == "DRAFT"
        assert char["content_hash"], "content hash must be computed at creation"
        assert len(char["content_hash"]) == 64, "content hash must be a full SHA-256"
        assert char["current_revision_id"] == f"charrev-{char['id']}-v1"

    def test_update_records_immutable_revision_with_new_hash(self, client):
        pid = "proj-cyberpunk-01"
        char = client.post(f"/api/v3/projects/{pid}/characters", json={"name": "Rin"}).json()
        old_hash = char["content_hash"]

        r = client.patch(
            f"/api/v3/characters/{char['id']}",
            json={"biography": "Tin tặc tự do", "expected_version": char["version"]},
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["version"] == char["version"] + 1
        assert updated["content_hash"] != old_hash

        revs = client.get(f"/api/v3/characters/{char['id']}/revisions").json()
        versions = [rev["character_version"] for rev in revs]
        assert versions == [1, 2], "each mutation must pin an immutable revision"
        hashes = [rev["content_hash"] for rev in revs]
        assert hashes[0] == old_hash and hashes[1] == updated["content_hash"]
        # Snapshots are immutable pins: v1 keeps the original biography.
        assert revs[0]["snapshot"]["identity"]["biography"] == ""

    def test_source_lineage_recorded(self, client):
        pid = "proj-cyberpunk-01"
        char = client.post(f"/api/v3/projects/{pid}/characters", json={"name": "Lineage Probe"}).json()
        assert set(char["source_lineage"].keys()) == {
            "source_series_id",
            "source_story_bible_artifact_id",
            "source_screenplay_revision_id",
            "source_hash",
        }


class TestCanonSync:
    def test_sync_without_lock_fails_closed(self, client):
        r = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error_code"] == "SCREENPLAY_NOT_LOCKED"

    def test_sync_unknown_episode_404(self, client):
        r = client.post("/api/v3/episodes/ep-gate-missing/characters/actions/canon-sync")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "EPISODE_NOT_FOUND"

    def test_sync_proposes_adds_from_story_bible_and_applies(self, client):
        lock_payload = _lock(client, "ep-cb-001", "proj-cyberpunk-01")

        r = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync")
        assert r.status_code == 200, r.text
        proposal = r.json()
        assert proposal["status"] == "PROPOSED"
        assert proposal["episode_id"] == "ep-cb-001"
        lineage = proposal["lineage"]
        assert lineage["source_screenplay_revision_id"] == lock_payload["revision_id"]
        assert lineage["source_series_id"] == "proj-cyberpunk-01"
        assert lineage["source_story_bible_artifact_id"], "StoryBible artifact must be pinned"

        names = {a["character_name"]: a for a in proposal["actions"]}
        assert "Alex" in names and "Vesper-9" in names
        assert names["Alex"]["action"] == "ADD_CHARACTER"
        assert proposal["summary"]["ADD_CHARACTER"] == 2

        # Apply the Alex action -> character created in REVIEW_REQUIRED with lineage.
        alex_index = next(i for i, a in enumerate(proposal["actions"]) if a["character_name"] == "Alex")
        apply_r = client.post(
            f"/api/v3/canon-sync/{proposal['proposal_id']}/apply",
            json={"action_index": alex_index},
        )
        assert apply_r.status_code == 200, apply_r.text
        applied = apply_r.json()
        assert applied["applied_action"] == "ADD_CHARACTER"
        assert applied["character"]["identity"]["name"] == "Alex"
        assert applied["character"]["status"] == "REVIEW_REQUIRED"
        assert applied["character"]["source_lineage"]["source_screenplay_revision_id"] == lock_payload["revision_id"]

        # Re-sync: the applied character now matches -> NO_CHANGE, not duplicate.
        resync = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        resync_names = {a["character_name"]: a["action"] for a in resync["actions"]}
        assert resync_names["Alex"] == "NO_CHANGE"
        assert resync_names["Vesper-9"] == "ADD_CHARACTER"

    def test_manual_edit_becomes_conflict_never_overwritten(self, client):
        _lock(client, "ep-cb-001", "proj-cyberpunk-01")
        proposal = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        alex_index = next(i for i, a in enumerate(proposal["actions"]) if a["character_name"] == "Alex")
        applied = client.post(
            f"/api/v3/canon-sync/{proposal['proposal_id']}/apply",
            json={"action_index": alex_index},
        ).json()
        char_id = applied["character"]["id"]

        # Manual edit AFTER the sync breaks the sync baseline...
        r = client.patch(
            f"/api/v3/characters/{char_id}",
            json={"biography": "Câu chuyện riêng do người viết tay", "expected_version": applied["character"]["version"]},
        )
        assert r.status_code == 200, r.text

        # ...so the next sync must propose a CONFLICT, not an overwrite.
        resync = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        alex_action = next(a for a in resync["actions"] if a["character_name"] == "Alex")
        assert alex_action["action"] == "CONFLICT"

        # Applying a CONFLICT is refused — resolution is manual/policy-driven.
        conflict_index = resync["actions"].index(alex_action)
        apply_r = client.post(
            f"/api/v3/canon-sync/{resync['proposal_id']}/apply",
            json={"action_index": conflict_index},
        )
        assert apply_r.status_code == 409
        assert apply_r.json()["detail"]["error_code"] == "ACTION_NOT_APPLICABLE"

        # The manual biography survived untouched.
        assert client.get(f"/api/v3/characters/{char_id}").json()["identity"]["biography"] == (
            "Câu chuyện riêng do người viết tay"
        )

    def test_no_change_apply_refused(self, client):
        _lock(client, "ep-cb-001", "proj-cyberpunk-01")
        first = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        alex_index = next(i for i, a in enumerate(first["actions"]) if a["character_name"] == "Alex")
        client.post(f"/api/v3/canon-sync/{first['proposal_id']}/apply", json={"action_index": alex_index})
        second = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        no_change_index = next(
            i for i, a in enumerate(second["actions"]) if a["action"] == "NO_CHANGE"
        )
        r = client.post(
            f"/api/v3/canon-sync/{second['proposal_id']}/apply",
            json={"action_index": no_change_index},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "ACTION_NOT_APPLICABLE"

    def test_unknown_proposal_404(self, client):
        r = client.get("/api/v3/canon-sync/cansync-gate-missing")
        assert r.status_code == 404
        r2 = client.post(
            "/api/v3/canon-sync/cansync-gate-missing/apply",
            json={"action_index": 0},
        )
        assert r2.status_code == 404


class TestReadinessLadder:
    def _make_character(self, client) -> dict:
        return client.post(
            "/api/v3/projects/proj-cyberpunk-01/characters",
            json={"name": "Ladder Probe", "role": "Protagonist"},
        ).json()

    def test_ladder_advances_one_step_at_a_time(self, client):
        char = self._make_character(client)
        r = client.post(
            f"/api/v3/characters/{char['id']}/actions/set-status",
            json={"status": "PRODUCTION_READY", "expected_version": char["version"]},
        )
        assert r.status_code == 409, "cannot skip the ladder"
        assert r.json()["detail"]["error_code"] == "INVALID_CHARACTER_STATUS_TRANSITION"

    def test_unknown_status_422(self, client):
        char = self._make_character(client)
        r = client.post(
            f"/api/v3/characters/{char['id']}/actions/set-status",
            json={"status": "GODMODE", "expected_version": char["version"]},
        )
        assert r.status_code == 422

    def test_production_ready_gated_on_required_fields(self, client):
        char = self._make_character(client)
        # Walk to APPROVED without filling readiness fields.
        version = char["version"]
        for target in ("REVIEW_REQUIRED", "APPROVED"):
            r = client.post(
                f"/api/v3/characters/{char['id']}/actions/set-status",
                json={"status": target, "expected_version": version},
            )
            assert r.status_code == 200, r.text
            version = r.json()["version"]

        r = client.post(
            f"/api/v3/characters/{char['id']}/actions/set-status",
            json={"status": "PRODUCTION_READY", "expected_version": version},
        )
        assert r.status_code == 409, "PRODUCTION_READY must be gated"
        detail = r.json()["detail"]
        assert detail["error_code"] == "CHARACTER_NOT_PRODUCTION_READY"
        assert "visual_profile.physical_description" in detail["missing_fields"]
        assert "continuity constraints" in detail["missing_fields"]

        # Fill the gaps, then the ladder completes.
        final = _make_production_ready(client, char["id"], expected_version=version)
        assert final["status"] == "PRODUCTION_READY"

    def test_version_pinning_survives_later_edits(self, client):
        char = self._make_character(client)
        pinned = _make_production_ready(client, char["id"])
        pinned_hash = pinned["content_hash"]
        pinned_version = pinned["version"]

        # A later manual edit bumps version/hash but the pinned values stand.
        r = client.patch(
            f"/api/v3/characters/{char['id']}",
            json={"biography": "Đã đổi sau khi pin", "expected_version": pinned_version},
        )
        assert r.status_code == 200, r.text
        after = r.json()
        assert after["content_hash"] != pinned_hash
        assert after["version"] == pinned_version + 1

        revs = client.get(f"/api/v3/characters/{char['id']}/revisions").json()
        pinned_rev = next(rev for rev in revs if rev["character_version"] == pinned_version)
        assert pinned_rev["content_hash"] == pinned_hash, "pinned revision must stay immutable"
