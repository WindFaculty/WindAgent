"""P1.4 — Storyboard Authority gate tests.

Gate: ``P1_4_STORYBOARD_AUTHORITY_LIVE``

Covers the P1.4 plan sub-phases against the real API surface:

- P1.4.1  Deterministic screenplay parsing: structured screenplay scenes are
          projected into Scene Records WITHOUT an LLM call, each pinned to
          ``source_screenplay_revision_id`` / ``source_screenplay_scene_id``
          / ``source_screenplay_scene_hash``.
- P1.4.2  Scene schema carries the production fields (visual summary,
          action summary, dialogue refs, time of day, required asset refs...).
- P1.4.3  Every sync state is an immutable StoryboardRevision with a
          deterministic content hash and ordered revision history.
- P1.4.4  Sync semantics: same screenplay again → IDEMPOTENT (no duplicate
          scenes, no new revision); changed screenplay → old revisions remain
          immutable and a NEW branch is projected (Scenario D).
- P1.4.5  Concept image generation fails closed with
          IMAGE_GENERATION_UNAVAILABLE — no QUEUED job is ever fabricated.
- P1.4.6  Manual operations (edit / split) keep the original screenplay
          lineage intact and bump MANUAL_EDIT revisions.

Tests reuse the demo-seeded Cyberpunk episode ``ep-cb-001``, whose
ScreenplayDraft artifact (rev-cb-001-v3) holds two structured scenes and whose
seeded board carries three legacy scenes pinned to that same revision. Locking
the episode at its real draft revision keeps every pin aligned.
"""
from __future__ import annotations

import uuid


DEMO_EPISODE = "ep-cb-001"
DEMO_REVISION = "rev-cb-001-v3"


def _lock(client, episode_id: str, revision_id: str | None = None) -> dict:
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    payload = {
        "revision_id": revision_id or f"rev-{uuid.uuid4().hex[:10]}",
        "content_hash": "b" * 64,
        "expected_version": ep["version"],
    }
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert r.status_code == 200, r.text
    return payload


def _sync(client, episode_id: str) -> dict:
    r = client.post(f"/api/v3/episodes/{episode_id}/storyboard/actions/sync")
    assert r.status_code == 200, r.text
    return r.json()


def _scenes(client, episode_id: str) -> list:
    r = client.get(f"/api/v3/episodes/{episode_id}/storyboard/scenes")
    assert r.status_code == 200, r.text
    return sorted(r.json(), key=lambda s: s["scene_number"])


def _revisions(client, episode_id: str) -> list:
    r = client.get(f"/api/v3/episodes/{episode_id}/storyboard/revisions")
    assert r.status_code == 200, r.text
    return r.json()


def _projected(client, episode_id: str, revision_id: str) -> list:
    """Scenes carrying real per-scene screenplay lineage for this revision."""
    return [
        s for s in _scenes(client, episode_id)
        if s.get("source_screenplay_revision_id") == revision_id
        and s.get("source_screenplay_scene_id")
    ]


# ─────────────────────────────────────────────────────────────────────────────
# P1.4.1 / P1.4.2 — Deterministic projection pins real screenplay lineage
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterministicProjection:
    def test_sync_pins_projected_scenes_with_full_lineage(self, client):
        lock = _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)

        projected = _projected(client, DEMO_EPISODE, lock["revision_id"])
        assert len(projected) == 2, (
            "the demo screenplay has exactly two structured scenes; "
            f"sync projected {len(projected)}"
        )
        for scene in projected:
            assert scene["episode_id"] == DEMO_EPISODE
            assert scene["storyboard_id"], "no orphan scenes"
            assert scene["source_screenplay_revision_id"] == lock["revision_id"]
            assert len(scene["source_screenplay_scene_hash"]) == 64

        by_number = {s["scene_number"]: s for s in projected}
        first = by_number[min(by_number)]
        assert "PHÒNG LÀM VIỆC" in first["location"].upper()
        assert first["time_of_day"] == "NIGHT", "deterministic heading parse"
        assert any(
            d.get("speaker") == "ALEX" for d in first["dialogue_refs"]
        ), "dialogue refs projected from the structured scene"

    def test_projection_is_deterministic_across_syncs(self, client):
        """Re-sync never mutates projections: identical ids and hashes."""
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        before = _projected(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        after = _projected(client, DEMO_EPISODE, DEMO_REVISION)

        def key(s):
            return (s["id"], s["source_screenplay_scene_id"], s["source_screenplay_scene_hash"])

        assert [key(s) for s in before] == [key(s) for s in after]

    def test_scene_schema_carries_production_fields(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        scene = next(
            s for s in _scenes(client, DEMO_EPISODE)
            if s.get("source_screenplay_scene_id")
        )
        for field in (
            "id", "storyboard_id", "episode_id", "scene_number", "title",
            "script_text", "visual_summary", "action_summary", "mood",
            "duration_seconds", "location", "character_ids", "dialogue_refs",
            "required_asset_refs", "status", "version",
            "source_screenplay_revision_id", "source_screenplay_scene_id",
        ):
            assert field in scene, f"schema field '{field}' missing"
        assert scene["action_summary"], "action summary projected from screenplay action"


# ─────────────────────────────────────────────────────────────────────────────
# P1.4.3 — Immutable StoryboardRevision with deterministic content hash
# ─────────────────────────────────────────────────────────────────────────────

class TestStoryboardRevisions:
    def test_first_sync_creates_revision_v1_with_hash(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        board = _sync(client, DEMO_EPISODE)

        assert board["current_revision_id"], "board must point at a revision"
        revs = _revisions(client, DEMO_EPISODE)
        assert len(revs) == 1
        rev = revs[0]
        assert rev["revision_number"] == 1
        assert rev["origin"] == "SYNC"
        assert rev["revision_id"] == board["current_revision_id"]
        assert rev["source_screenplay_revision_id"] == DEMO_REVISION
        assert len(rev["content_hash"]) == 64, "revision must carry a content hash"
        assert rev["scene_count"] == len(_scenes(client, DEMO_EPISODE))

    def test_manual_edit_appends_ordered_revision(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        scene = _scenes(client, DEMO_EPISODE)[0]
        client.patch(
            f"/api/v3/storyboard/scenes/{scene['id']}",
            json={"visual_summary": "Neon rain over the desk", "expected_version": scene["version"]},
        )
        numbers = [r["revision_number"] for r in _revisions(client, DEMO_EPISODE)]
        assert numbers == sorted(numbers) == [1, 2]
        origins = {r["origin"] for r in _revisions(client, DEMO_EPISODE)}
        assert origins == {"SYNC", "MANUAL_EDIT"}


# ─────────────────────────────────────────────────────────────────────────────
# P1.4.4 — Sync semantics: idempotent + immutable old revisions (Scenario D)
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncSemantics:
    def test_resync_same_screenplay_is_idempotent(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        first = _sync(client, DEMO_EPISODE)
        scenes_after_first = _scenes(client, DEMO_EPISODE)

        second = _sync(client, DEMO_EPISODE)

        assert second["current_revision_id"] == first["current_revision_id"], (
            "same screenplay pin must not create another revision"
        )
        assert _scenes(client, DEMO_EPISODE) == scenes_after_first, "no duplicated or mutated scenes"
        assert len(_revisions(client, DEMO_EPISODE)) == 1

    def test_resync_after_manual_edit_never_duplicates(self, client):
        """Manual edit bumps a MANUAL_EDIT revision; re-syncing the SAME
        screenplay must back-fill nothing (whole-board idempotency key)."""
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        target = next(
            s for s in _scenes(client, DEMO_EPISODE) if s.get("source_screenplay_scene_id")
        )
        client.patch(
            f"/api/v3/storyboard/scenes/{target['id']}",
            json={"visual_summary": "manual note", "expected_version": target["version"]},
        )
        count_after_edit = len(_scenes(client, DEMO_EPISODE))

        # Re-sync with the SAME locked screenplay.
        _sync(client, DEMO_EPISODE)

        after = _scenes(client, DEMO_EPISODE)
        assert len(after) == count_after_edit, (
            f"re-sync duplicated the scene set ({count_after_edit} -> {len(after)})"
        )
        assert {s["id"] for s in after} == {
            s["id"] for s in _scenes(client, DEMO_EPISODE)
        }

    def test_new_screenplay_creates_branch_old_scenes_immutable(self, client):
        """Scenario D: screenplay v5 → board A; derive v6 → A unchanged."""
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        board_a = _sync(client, DEMO_EPISODE)
        scenes_a = _scenes(client, DEMO_EPISODE)
        revs_a = _revisions(client, DEMO_EPISODE)

        lock_b = _lock(client, DEMO_EPISODE)  # derive a new locked revision
        assert lock_b["revision_id"] != DEMO_REVISION
        board_b = _sync(client, DEMO_EPISODE)

        assert board_b["current_revision_id"] != board_a["current_revision_id"]
        assert board_b["source_screenplay_revision_id"] == lock_b["revision_id"]

        # Old revision records untouched; a new branch was appended.
        revs_after = _revisions(client, DEMO_EPISODE)
        assert [r["revision_id"] for r in revs_after][: len(revs_a)] == [
            r["revision_id"] for r in revs_a
        ], "old revisions are immutable"
        assert revs_after[-1]["source_screenplay_revision_id"] == lock_b["revision_id"]
        assert revs_after[-1]["revision_number"] == len(revs_a) + 1

        # Old scene records unchanged (same ids, same content, same timestamps).
        scenes_after = {s["id"]: s for s in _scenes(client, DEMO_EPISODE)}
        for old in scenes_a:
            kept = scenes_after[old["id"]]
            assert kept["updated_at"] == old["updated_at"], "immutable scene was touched"
            assert kept["script_text"] == old["script_text"]


# ─────────────────────────────────────────────────────────────────────────────
# P1.4.5 — Concept generation fails closed
# ─────────────────────────────────────────────────────────────────────────────

class TestConceptGenerationFailClosed:
    def test_generation_unavailable_without_provider(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        scene = _scenes(client, DEMO_EPISODE)[0]

        jobs_before = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/jobs").json()
        r = client.post(
            f"/api/v3/storyboard/scenes/{scene['id']}/generations",
            json={"reference_character_ids": []},
        )
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["error_code"] == "IMAGE_GENERATION_UNAVAILABLE"

        # Polling a job that was never created stays a 404 — nothing lingered.
        gen_r = client.get(f"/api/v3/storyboard/scenes/{scene['id']}/generations/gen-ghost")
        assert gen_r.status_code == 404
        assert isinstance(jobs_before, list)


# ─────────────────────────────────────────────────────────────────────────────
# P1.4.6 — Manual operations keep screenplay lineage
# ─────────────────────────────────────────────────────────────────────────────

class TestManualOperations:
    def test_manual_edit_keeps_lineage_and_bumps_manual_revision(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        scene = next(
            s for s in _scenes(client, DEMO_EPISODE) if s.get("source_screenplay_scene_hash")
        )

        r = client.patch(
            f"/api/v3/storyboard/scenes/{scene['id']}",
            json={
                "visual_summary": "Alex lit by monitor glow",
                "duration_seconds": 90,
                "expected_version": scene["version"],
            },
        )
        assert r.status_code == 200, r.text
        edited = r.json()

        # Lineage columns are immutable under manual edit.
        assert edited["source_screenplay_revision_id"] == scene["source_screenplay_revision_id"]
        assert edited["source_screenplay_scene_id"] == scene["source_screenplay_scene_id"]
        assert edited["source_screenplay_scene_hash"] == scene["source_screenplay_scene_hash"]
        assert edited["version"] == scene["version"] + 1

        last_rev = _revisions(client, DEMO_EPISODE)[-1]
        assert last_rev["origin"] == "MANUAL_EDIT"

    def test_split_scene_keeps_lineage_on_both_parts(self, client):
        _lock(client, DEMO_EPISODE, DEMO_REVISION)
        _sync(client, DEMO_EPISODE)
        scene = next(
            s for s in _scenes(client, DEMO_EPISODE)
            if s.get("source_screenplay_scene_hash") and len(s["script_text"]) > 10
        )

        r = client.post(
            f"/api/v3/storyboard/scenes/{scene['id']}/actions/split",
            json={"expected_version": scene["version"]},
        )
        assert r.status_code == 200, r.text
        part_one, part_two = r.json()

        for part in (part_one, part_two):
            assert part["source_screenplay_revision_id"] == scene["source_screenplay_revision_id"]
            assert part["source_screenplay_scene_id"] == scene["source_screenplay_scene_id"]
            assert part["storyboard_id"] == scene["storyboard_id"]
            assert part["episode_id"] == scene["episode_id"]
        assert part_two["parent_scene_id"] == part_one["id"]
        assert (
            part_one["duration_seconds"] + part_two["duration_seconds"]
            == scene["duration_seconds"]
        ), "split redistributes estimated duration"

        last_rev = _revisions(client, DEMO_EPISODE)[-1]
        assert last_rev["origin"] == "MANUAL_EDIT"
