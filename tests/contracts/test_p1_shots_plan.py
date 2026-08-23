"""P1.5 — Production Shot Planning gate tests.

Gate: ``P1_5_SHOT_PLANNING_LIVE``

Covers the P1.5 plan sub-phases against the real API surface:

- P1.5.1  Deterministic shot generation: scenes without shots are backfilled
          by a rule-based projection (NO LLM) whose shot durations sum exactly
          to the scene duration; re-runs are idempotent and never clobber
          manual or seeded work.
- P1.5.2  Truth rules: GET /shot-plan never fabricates a plan (404), generate
          fails closed without a synced storyboard (409 STORYBOARD_NOT_SYNCED).
- P1.5.3/4  Structural validation detects real timing drift in the seeded
          data (SHOT_DURATION_MISMATCH) and dangling references; once a
          producer fixes the timings through the public API the plan
          validates clean.
- P1.5.5  Pin semantics: pinning snapshots every shot under a deterministic
          content hash and freezes the plan (every mutation 409s with
          SHOT_PLAN_PINNED); derive restores an editable DRAFT from the frozen
          snapshot; manual ops (reorder/split/merge/delete) keep server-side
          optimistic locking.

Tests reuse the demo-seeded Cyberpunk episode ``ep-cb-001`` (locked at its
real draft revision rev-cb-001-v3, storyboard synced) which carries three
seeded shots whose durations now match their scene lengths (70+80=150 and
105=105); timing drift must be introduced artificially to test the validator.
"""
from __future__ import annotations

import uuid


DEMO_EPISODE = "ep-cb-001"
DEMO_REVISION = "rev-cb-001-v3"
DEMO_PROJECT = "proj-cyberpunk-01"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lock(client, episode_id: str = DEMO_EPISODE, revision_id: str | None = None) -> dict:
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    payload = {
        "revision_id": revision_id or f"rev-{uuid.uuid4().hex[:10]}",
        "content_hash": "c" * 64,
        "expected_version": ep["version"],
    }
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert r.status_code == 200, r.text
    return payload


def _sync(client, episode_id: str = DEMO_EPISODE) -> dict:
    r = client.post(f"/api/v3/episodes/{episode_id}/storyboard/actions/sync")
    assert r.status_code == 200, r.text
    return r.json()


def _generate(client, episode_id: str = DEMO_EPISODE):
    return client.post(
        f"/api/v3/episodes/{episode_id}/production/shot-plan/actions/generate"
    )


def _plan(client, episode_id: str = DEMO_EPISODE):
    return client.get(f"/api/v3/episodes/{episode_id}/production/shot-plan")


def _validation(client, episode_id: str = DEMO_EPISODE):
    return client.get(
        f"/api/v3/episodes/{episode_id}/production/shot-plan/validation"
    )


def _scenes(client, episode_id: str = DEMO_EPISODE) -> list:
    r = client.get(f"/api/v3/episodes/{episode_id}/storyboard/scenes")
    assert r.status_code == 200, r.text
    return sorted(r.json(), key=lambda s: s["scene_number"])


def _new_episode(client, title: str = "Shot Plan Probe") -> str:
    r = client.post(
        f"/api/v3/projects/{DEMO_PROJECT}/episodes",
        json={"title": title},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _fix_seeded_timings(client, episode_id: str = DEMO_EPISODE) -> None:
    """Repair the seeded duration drift through the public PATCH endpoint."""
    targets = {"shot-cb-001-01": 70, "shot-cb-001-02": 80, "shot-cb-001-03": 105}
    r = client.get(f"/api/v3/episodes/{episode_id}/shots")
    assert r.status_code == 200, r.text
    for shot in r.json():
        if shot["id"] not in targets:
            continue
        r = client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={"duration_seconds": targets[shot["id"]], "expected_version": shot["version"]},
        )
        assert r.status_code == 200, r.text


def _blocking(validation: dict) -> list:
    return [f for f in validation["findings"] if f["severity"] == "BLOCKING"]


# ─────────────────────────────────────────────────────────────────────────────
# P1.5.2 — GET truth + fail-closed generation
# ─────────────────────────────────────────────────────────────────────────────

class TestShotPlanTruth:
    def test_get_plan_before_generate_is_404(self, client):
        eid = _new_episode(client)
        r = _plan(client, eid)
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "SHOT_PLAN_NOT_CREATED"

    def test_generate_without_storyboard_fails_closed(self, client):
        eid = _new_episode(client)
        r = _generate(client, eid)
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "STORYBOARD_NOT_SYNCED"
        # The failed attempt must not have fabricated a plan as a side effect.
        after = _plan(client, eid)
        assert after.status_code == 404

    def test_validation_endpoint_never_creates_state(self, client):
        eid = _new_episode(client)
        first = _validation(client, eid)
        second = _validation(client, eid)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json(), "read-only validation is deterministic"
        assert _plan(client, eid).status_code == 404, "no plan was created by reads"


# ─────────────────────────────────────────────────────────────────────────────
# P1.5.1 — Deterministic generation
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterministicGeneration:
    def test_generate_backfills_every_uncovered_scene(self, client):
        _lock(client)
        _sync(client)
        scenes = {s["id"]: s for s in _scenes(client)}
        seeded_ids = {"shot-cb-001-01", "shot-cb-001-02", "shot-cb-001-03"}

        r = _generate(client)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["generated_count"] > 0

        plan = _plan(client).json()
        assert plan["status"] == "DRAFT"

        by_scene: dict[str, list] = {}
        for shot in plan["shots"]:
            if shot["id"] in seeded_ids:
                continue  # seeded drift is validated separately
            by_scene.setdefault(shot["scene_id"], []).append(shot)

        # Every scene that received generated shots must sum exactly to its
        # scene duration and carry a continuous chain.
        for sid, shots in by_scene.items():
            total = sum(int(s["duration_seconds"]) for s in shots)
            assert total == int(scenes[sid]["duration_seconds"]), (
                f"scene {sid}: shots sum {total} != scene duration"
            )
            ordered = sorted(shots, key=lambda s: s["shot_number"])
            assert ordered[0]["continuity_from"] is None
            for prev, nxt in zip(ordered, ordered[1:]):
                assert nxt["continuity_from"] == prev["id"]
                assert prev["continuity_to"] == nxt["id"]

    def test_generation_is_idempotent(self, client):
        _lock(client)
        _sync(client)
        first = _generate(client).json()
        plan_after_first = _plan(client).json()
        ids_first = [s["id"] for s in plan_after_first["shots"]]
        assert first["generated_count"] > 0

        second = _generate(client).json()

        assert second["generated_count"] == 0, "backfill must be idempotent"
        plan_after_second = _plan(client).json()
        assert [s["id"] for s in plan_after_second["shots"]] == ids_first

    def test_seed_work_is_never_clobbered(self, client):
        _lock(client)
        _sync(client)
        _generate(client)

        plan = _plan(client).json()
        seeded = {s["id"]: s for s in plan["shots"] if s["id"].startswith("shot-cb-001")}
        assert set(seeded) == {
            "shot-cb-001-01", "shot-cb-001-02", "shot-cb-001-03",
        }, "existing seeded shots must survive generation untouched"
        assert int(seeded["shot-cb-001-01"]["duration_seconds"]) == 70
        assert int(seeded["shot-cb-001-02"]["duration_seconds"]) == 80
        assert int(seeded["shot-cb-001-03"]["duration_seconds"]) == 105


# ─────────────────────────────────────────────────────────────────────────────
# P1.5.3/P1.5.4 — Structural validation
# ─────────────────────────────────────────────────────────────────────────────

class TestValidation:
    def test_seeded_timing_drift_is_detected(self, client):
        """After fixing the canonical seed, the seeded timings are valid —
        but artificially introduced drift must still be flagged."""
        _lock(client)
        _sync(client)
        _generate(client)

        # Baseline is now VALID
        body = _validation(client).json()
        assert body["status"] == "VALID", body["findings"]

        # Introduce drift: patch one shot to break scene total
        plan = _plan(client).json()
        victim = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-01")
        r = client.patch(f"/api/v3/shots/{victim['id']}", json={"duration_seconds": 1, "expected_version": victim["version"]})
        assert r.status_code == 200, r.text

        drifted = _validation(client).json()
        assert drifted["status"] == "INVALID"
        mismatch_scenes = {
            f["scene_id"] for f in _blocking(drifted)
            if f["code"] == "SHOT_DURATION_MISMATCH"
        }
        assert "scene-cb-001-01" in mismatch_scenes, (
            "1+80=81s of shots vs a 150s scene must be flagged"
        )

    def test_fixed_timings_validate_clean(self, client):
        _lock(client)
        _sync(client)
        _fix_seeded_timings(client)
        _generate(client)

        body = _validation(client).json()
        assert body["status"] == "VALID", body["findings"]
        assert _blocking(body) == []

    def test_dangling_character_reference_blocks(self, client):
        _lock(client)
        _sync(client)
        _generate(client)
        plan = _plan(client).json()
        shot = plan["shots"][0]

        r = client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={
                "subject_character_refs": ["char-ghost"],
                "expected_version": shot["version"],
            },
        )
        assert r.status_code == 200, r.text

        body = _validation(client).json()
        codes = {f["code"] for f in _blocking(body)}
        assert "UNRESOLVED_CHARACTER_REF" in codes

        # Repairing the reference clears the finding again.
        fresh = next(
            s for s in _plan(client).json()["shots"] if s["id"] == shot["id"]
        )
        client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={"subject_character_refs": [], "expected_version": fresh["version"]},
        )
        repaired_codes = {
            f["code"] for f in _blocking(_validation(client).json())
            if f.get("shot_id") == shot["id"]
        }
        assert "UNRESOLVED_CHARACTER_REF" not in repaired_codes

    def test_totals_report_scene_vs_shot_seconds(self, client):
        _lock(client)
        _sync(client)
        _generate(client)
        totals = _validation(client).json()["totals"]
        assert totals["scenes"] == len(_scenes(client))
        assert totals["shots"] == len(_plan(client).json()["shots"])
        assert isinstance(totals["planned_shot_seconds"], int)
        assert isinstance(totals["scene_seconds"], int)


# ─────────────────────────────────────────────────────────────────────────────
# P1.5.5 — Pin / derive / immutability
# ─────────────────────────────────────────────────────────────────────────────

class TestPinSemantics:
    def _prepared(self, client):
        _lock(client)
        _sync(client)
        _fix_seeded_timings(client)
        _generate(client)
        return _plan(client).json()

    def test_pin_snapshots_and_locks_plan(self, client):
        plan = self._prepared(client)
        count = len(plan["shots"])

        r = client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")
        assert r.status_code == 200, r.text
        pinned = r.json()

        assert pinned["status"] == "PINNED"
        assert pinned["current_revision_id"] == "sprev-ep-cb-001-v1"
        assert len(pinned["content_hash"]) == 64
        assert pinned["shot_count"] == count

        after = _plan(client).json()
        assert after["status"] == "PINNED"
        assert after["current_revision_id"] == pinned["current_revision_id"]

    def test_pinned_plan_rejects_every_mutation(self, client):
        plan = self._prepared(client)
        shot = plan["shots"][0]
        other = plan["shots"][1]
        client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")

        def expect_pinned(r):
            assert r.status_code == 409, r.text
            assert r.json()["detail"]["error_code"] == "SHOT_PLAN_PINNED"

        expect_pinned(client.patch(
            f"/api/v3/shots/{shot['id']}",
            json={"action": "hack", "expected_version": shot["version"]},
        ))
        expect_pinned(client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/shots",
            json={"duration_seconds": 5},
        ))
        expect_pinned(client.delete(f"/api/v3/shots/{other['id']}"))
        expect_pinned(client.post(
            f"/api/v3/shots/{shot['id']}/actions/reorder",
            json={"new_position": 1, "expected_version": shot["version"]},
        ))
        expect_pinned(client.post(
            f"/api/v3/shots/{shot['id']}/actions/split",
            json={"expected_version": shot["version"]},
        ))
        expect_pinned(client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/shots/actions/merge",
            json={
                "shot_ids": [shot["id"], other["id"]],
                "expected_versions": {shot["id"]: shot["version"], other["id"]: other["version"]},
            },
        ))
        expect_pinned(_generate(client))

    def test_derive_restores_editable_draft(self, client):
        self._prepared(client)
        pinned_before = {
            s["id"] for s in _plan(client).json()["shots"]
        }
        client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")
        pinned_revision = _plan(client).json()["current_revision_id"]

        r = client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/derive")
        assert r.status_code == 200, r.text
        derived = r.json()

        assert derived["status"] == "DRAFT"
        assert derived["derived_from"] == pinned_revision
        assert derived["restored_shot_count"] == len(pinned_before)

        plan = _plan(client).json()
        new_ids = {s["id"] for s in plan["shots"]}
        assert new_ids.isdisjoint(pinned_before), "derive must mint fresh shot ids"

        # Editing works again on the derived draft.
        target = plan["shots"][0]
        r = client.patch(
            f"/api/v3/shots/{target['id']}",
            json={"action": "post-derive edit", "expected_version": target["version"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["action"] == "post-derive edit"

    def test_repin_hash_reflects_edits(self, client):
        self._prepared(client)
        first_pin = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin"
        ).json()
        hash_one = first_pin["content_hash"]

        client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/derive")
        target = _plan(client).json()["shots"][0]
        client.patch(
            f"/api/v3/shots/{target['id']}",
            json={"composition_notes": "changed framing intent", "expected_version": target["version"]},
        )

        second_pin = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin"
        ).json()

        assert second_pin["content_hash"] != hash_one, (
            "the pinned content hash must track actual shot content"
        )
        assert second_pin["current_revision_id"] != first_pin["current_revision_id"]

    def test_empty_plan_cannot_pin(self, client):
        eid = _new_episode(client, "Pin Probe")
        r = client.post(f"/api/v3/episodes/{eid}/production/shot-plan/actions/pin")
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "SHOT_PLAN_EMPTY"

    def test_derive_without_pin_fails_closed(self, client):
        eid = _new_episode(client, "Derive Probe")
        r = client.post(f"/api/v3/episodes/{eid}/production/shot-plan/actions/derive")
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "SHOT_PLAN_NOT_PINNED"


# ─────────────────────────────────────────────────────────────────────────────
# P1.5.5 — Manual operations (reorder / split / merge / delete)
# ─────────────────────────────────────────────────────────────────────────────

class TestManualOperations:
    def _prepared(self, client):
        _lock(client)
        _sync(client)
        r = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/shots")
        assert r.status_code == 200, r.text
        return {"shots": sorted(r.json(), key=lambda s: s["shot_number"])}

    def test_merge_consecutive_same_scene_shots(self, client):
        plan = self._prepared(client)
        first = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-01")
        second = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-02")

        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/shots/actions/merge",
            json={
                "shot_ids": [first["id"], second["id"]],
                "expected_versions": {first["id"]: first["version"], second["id"]: second["version"]},
            },
        )
        assert r.status_code == 200, r.text
        merged = r.json()
        assert merged["id"] == first["id"], "the earlier shot absorbs the later one"
        assert merged["duration_seconds"] == (
            int(first["duration_seconds"]) + int(second["duration_seconds"])
        )
        assert merged["continuity_to"] == second.get("continuity_to")

        gone = client.get(f"/api/v3/shots/{second['id']}")
        assert gone.status_code == 404

    def test_merge_rejects_cross_scene_pair(self, client):
        plan = self._prepared(client)
        second = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-02")
        third = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-03")

        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/shots/actions/merge",
            json={
                "shot_ids": [second["id"], third["id"]],
                "expected_versions": {second["id"]: second["version"], third["id"]: third["version"]},
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "MERGE_ACROSS_SCENES"

    def test_split_shot_redistributes_duration_and_links_continuity(self, client):
        plan = self._prepared(client)
        target = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-03")

        r = client.post(
            f"/api/v3/shots/{target['id']}/actions/split",
            json={"expected_version": target["version"], "split_seconds": 3},
        )
        assert r.status_code == 200, r.text
        part_one, part_two = r.json()

        assert part_one["id"] == target["id"]
        assert part_one["duration_seconds"] == 3
        assert part_two["duration_seconds"] == int(target["duration_seconds"]) - 3
        assert part_two["continuity_from"] == part_one["id"]
        assert part_one["continuity_to"] == part_two["id"]
        assert part_two["continuity_to"] == target.get("continuity_to")

    def test_split_out_of_range_fails_closed(self, client):
        plan = self._prepared(client)
        target = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-03")

        # shot-cb-001-03 is 105s after fix; 106 is out of range
        r = client.post(
            f"/api/v3/shots/{target['id']}/actions/split",
            json={"expected_version": target["version"], "split_seconds": 106},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["error_code"] == "SPLIT_OUT_OF_RANGE"

    def test_reorder_moves_shot_within_episode(self, client):
        plan = self._prepared(client)
        third = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-03")

        r = client.post(
            f"/api/v3/shots/{third['id']}/actions/reorder",
            json={"new_position": 1, "expected_version": third["version"]},
        )
        assert r.status_code == 200, r.text

        r = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/shots")
        assert r.status_code == 200, r.text
        numbers = {
            s["id"]: s["shot_number"]
            for s in r.json()
        }
        assert numbers["shot-cb-001-03"] == 1
        assert numbers["shot-cb-001-01"] == 2
        assert numbers["shot-cb-001-02"] == 3
        assert sorted(numbers.values()) == sorted(set(numbers.values())), "no gaps/dupes"

    def test_reorder_with_stale_version_conflicts(self, client):
        plan = self._prepared(client)
        third = next(s for s in plan["shots"] if s["id"] == "shot-cb-001-03")

        r = client.post(
            f"/api/v3/shots/{third['id']}/actions/reorder",
            json={"new_position": 1, "expected_version": third["version"] + 5},
        )
        assert r.status_code == 409

    def test_delete_draft_shot(self, client):
        self._prepared(client)
        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/shots",
            json={"duration_seconds": 7, "shot_size": "CLOSE_UP"},
        )
        assert r.status_code == 201, r.text
        created = r.json()

        deleted = client.delete(f"/api/v3/shots/{created['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": created["id"]}
        assert client.get(f"/api/v3/shots/{created['id']}").status_code == 404
