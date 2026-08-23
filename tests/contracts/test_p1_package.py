"""P1.6 — Production Package & Readiness gate tests.

Gate: ``P1_6_PRODUCTION_PACKAGE_READY``

Covers the P1.6 plan sub-phases against the real API surface:

- P1.6.3  Preflight validator: read-only READY/BLOCKED with blocking findings
          for every real gap (screenplay not locked, storyboard lineage
          mismatch, shot plan not pinned, characters not production-ready,
          mandatory assets unfulfilled). A GET never mutates and never
          fabricates readiness.
- P1.6.5  Finalize: content-addressed immutable package. Unchanged content
          re-finalizes to the SAME package id; changed content creates a NEW
          package while the old one stays byte-identical.
- P1.6.2  production_target is stored metadata only — no engine is executed.
- P1.6.6  Invalidation: deriving the screenplay or shots never touches an
          existing finalized package.

The happy path drives the demo-seeded Cyberpunk episode ``ep-cb-001`` through
the FULL public pipeline: lock → storyboard sync → requirement sync → shot
timing repairs → deterministic generation → canon promotion → asset
fulfilment (verified bytes) → pin → finalize.
"""
from __future__ import annotations

import base64
import uuid


DEMO_EPISODE = "ep-cb-001"
DEMO_REVISION = "rev-cb-001-v3"
DEMO_PROJECT = "proj-cyberpunk-01"

# Seeded shots drift from their scene lengths; these values repair them so
# Σ shot seconds == scene seconds for scenes that already have shots.
_SEED_TIMING_FIX = {"shot-cb-001-01": 70, "shot-cb-001-02": 80, "shot-cb-001-03": 105}


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline helpers (all through the public API)
# ─────────────────────────────────────────────────────────────────────────────

def _lock(client, episode_id: str = DEMO_EPISODE, revision_id: str | None = None) -> dict:
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    payload = {
        "revision_id": revision_id or DEMO_REVISION,
        "content_hash": "d" * 64,
        "expected_version": ep["version"],
    }
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert r.status_code == 200, r.text
    return payload


def _sync_storyboard(client, episode_id: str = DEMO_EPISODE) -> dict:
    r = client.post(f"/api/v3/episodes/{episode_id}/storyboard/actions/sync")
    assert r.status_code == 200, r.text
    return r.json()


def _sync_requirements(client, episode_id: str = DEMO_EPISODE) -> list:
    r = client.post(f"/api/v3/episodes/{episode_id}/assets/requirements/actions/sync")
    assert r.status_code == 200, r.text
    return client.get(f"/api/v3/episodes/{episode_id}/assets/requirements").json()


def _generate_shots(client, episode_id: str = DEMO_EPISODE) -> dict:
    r = client.post(f"/api/v3/episodes/{episode_id}/production/shot-plan/actions/generate")
    assert r.status_code == 200, r.text
    return r.json()


def _pin_shots(client, episode_id: str = DEMO_EPISODE) -> dict:
    r = client.post(f"/api/v3/episodes/{episode_id}/production/shot-plan/actions/pin")
    assert r.status_code == 200, r.text
    return r.json()


def _fix_seed_timings(client, episode_id: str = DEMO_EPISODE) -> None:
    r = client.get(f"/api/v3/episodes/{episode_id}/shots")
    assert r.status_code == 200, r.text
    for shot in r.json():
        if shot["id"] in _SEED_TIMING_FIX:
            rr = client.patch(
                f"/api/v3/shots/{shot['id']}",
                json={"duration_seconds": _SEED_TIMING_FIX[shot["id"]], "expected_version": shot["version"]},
            )
            assert rr.status_code == 200, rr.text


def _promote_all_characters(client, project_id: str = DEMO_PROJECT) -> None:
    """Ladder every referenced character to PRODUCTION_READY."""
    r = client.get(f"/api/v3/projects/{project_id}/characters")
    assert r.status_code == 200, r.text
    for char in r.json():
        cid = char["id"]
        continuity = char.get("continuity") or {}
        if not (continuity.get("immutable_features") or continuity.get("wardrobe_rules")):
            rr = client.patch(
                f"/api/v3/characters/{cid}",
                json={
                    "immutable_features": ["silver hair", "grey eyes"],
                    "wardrobe_rules": ["dark long coat"],
                    "expected_version": char["version"],
                },
            )
            assert rr.status_code == 200, rr.text
            current = rr.json()
        else:
            current = char
        for next_status in ("REVIEW_REQUIRED", "APPROVED", "PRODUCTION_READY"):
            if current.get("status") == next_status:
                continue
            rr = client.post(
                f"/api/v3/characters/{cid}/actions/set-status",
                json={"status": next_status, "expected_version": current["version"]},
            )
            assert rr.status_code == 200, rr.text
            current = rr.json()


def _fulfill_mandatory_assets(client, episode_id: str = DEMO_EPISODE) -> None:
    """Create a verified asset per OPEN mandatory requirement and pin it."""
    reqs = client.get(f"/api/v3/episodes/{episode_id}/assets/requirements").json()
    for req in reqs:
        if not req.get("mandatory") or req.get("status") != "OPEN":
            continue
        raw = b"verified-bytes:" + req["requirement_id"].encode()
        r = client.post("/api/v3/assets", json={
            "name": f"Fulfil {req['name'] or req['requirement_id']}",
            "type": "IMAGE",
            "episode_id": episode_id,
            "project_id": DEMO_PROJECT,
            "requirement_id": req["requirement_id"],
            "content_base64": base64.b64encode(raw).decode(),
        })
        assert r.status_code == 201, r.text
        asset = r.json()
        # DRAFT -> REVIEW -> APPROVED via lifecycle steps...
        for next_status in ("REVIEW", "APPROVED"):
            rr = client.post(
                f"/api/v3/assets/{asset['id']}/actions/set-status",
                json={"status": next_status, "expected_version": asset["version"]},
            )
            assert rr.status_code == 200, rr.text
            asset = rr.json()
        # ...the approval pin is recorded against a SPECIFIC revision...
        rr = client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={"revision_id": asset["current_revision_id"], "approved_by": "p1-contract-test"},
        )
        assert rr.status_code == 200, rr.text
        asset = rr.json()
        # ...and only then can the asset be PINNED.
        rr = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "PINNED", "expected_version": asset["version"]},
        )
        assert rr.status_code == 200, rr.text


def _prepare_ready_episode(client) -> None:
    """Drive ep-cb-001 all the way to a READY preflight via public APIs."""
    _lock(client)
    _sync_storyboard(client)
    _sync_requirements(client)
    _fix_seed_timings(client)
    _generate_shots(client)
    _promote_all_characters(client)
    _fulfill_mandatory_assets(client)
    _pin_shots(client)


def _preflight(client, episode_id: str = DEMO_EPISODE):
    return client.get(f"/api/v3/episodes/{episode_id}/production/package/preflight")


def _blocking_codes(body: dict) -> set:
    return {f["code"] for f in body.get("blocking_findings", [])}


# ─────────────────────────────────────────────────────────────────────────────
# P1.6.3 — Preflight truth
# ─────────────────────────────────────────────────────────────────────────────

class TestPreflightTruth:
    def test_unprepared_episode_is_blocked_with_real_findings(self, client):
        body = _preflight(client).json()
        assert body["status"] == "BLOCKED"
        codes = _blocking_codes(body)
        assert "SCREENPLAY_NOT_LOCKED" in codes
        assert "SHOT_PLAN_NOT_PINNED" in codes
        assert "CHARACTERS_NOT_PRODUCTION_READY" in codes

    def test_preflight_never_mutates_state(self, client):
        first = _preflight(client).json()
        second = _preflight(client).json()
        assert first == second, "read-only preflight is deterministic"
        # No side-effect resources appeared.
        assert client.get(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan"
        ).status_code == 404
        packages = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/packages")
        assert packages.status_code == 200
        assert packages.json() == []

    def test_unknown_episode_404(self, client):
        r = _preflight(client, "ep-ghost")
        assert r.status_code == 404

    def test_lineage_mismatch_blocks_after_relock(self, client):
        """Scenario E: re-locking a NEW screenplay invalidates the old board."""
        _lock(client)
        _sync_storyboard(client)
        _lock(client, revision_id=f"rev-{uuid.uuid4().hex[:10]}")

        body = _preflight(client).json()
        assert body["status"] == "BLOCKED"
        assert "PREPRODUCTION_LINEAGE_MISMATCH" in _blocking_codes(body)

    def test_full_pipeline_reaches_ready(self, client):
        _prepare_ready_episode(client)

        body = _preflight(client).json()
        assert body["status"] == "READY", body["blocking_findings"]
        assert body["blocking_findings"] == []
        checks = body["checks"]
        for key in (
            "screenplay_locked",
            "storyboard_synced",
            "storyboard_hash_current",
            "shot_plan_pinned",
            "shots_valid",
            "characters_production_ready",
            "mandatory_assets_resolved",
        ):
            assert checks[key] is True, key


# ─────────────────────────────────────────────────────────────────────────────
# P1.6.5/P1.6.2 — Finalize: immutable content-addressed handoff
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalizePackage:
    def test_finalize_blocked_fails_closed(self, client):
        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        )
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["error_code"] == "PREPRODUCTION_NOT_READY"
        assert detail["blocking_findings"], "must carry the real blockers"
        # Nothing was persisted.
        assert client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/packages").json() == []

    def test_invalid_target_rejected(self, client):
        _prepare_ready_episode(client)
        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "MINECRAFT"},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["error_code"] == "INVALID_PRODUCTION_TARGET"

    def test_finalize_creates_content_addressed_manifest(self, client):
        _prepare_ready_episode(client)

        r = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "BLENDER"},
        )
        assert r.status_code == 201, r.text
        pkg = r.json()["package"]

        assert pkg["package_id"].startswith("pkg-")
        assert len(pkg["package_hash"]) == 64
        assert pkg["status"] == "FINALIZED"
        assert pkg["created_at"]
        # Target is stored metadata only (P1.6.2): no engine execution.
        assert pkg["production_target"] == "BLENDER"

        # §P1.6.1 manifest sections.
        assert pkg["locked_screenplay"]["revision_id"] == DEMO_REVISION
        assert len(pkg["locked_screenplay"]["content_hash"]) == 64
        assert pkg["character_canon"], "referenced characters pinned with hashes"
        for c in pkg["character_canon"]:
            assert c["hash"], f"character {c['character_id']} must carry a hash"
        assert pkg["world_canon"]["project_id"] == DEMO_PROJECT
        assert pkg["storyboard"]["revision_id"]
        assert len(pkg["storyboard"]["hash"]) == 64
        assert pkg["scenes"], "scene rows included"
        assert pkg["shot_plan"]["revision_id"] == "sprev-ep-cb-001-v1"
        assert pkg["shot_plan"]["shot_count"] > 0
        assert pkg["constraints"]["planned_shot_seconds"] > 0

        # Every pinned mandatory asset carries its approval pin hash.
        assert pkg["assets"], "mandatory assets were fulfilled and pinned"
        for a in pkg["assets"]:
            assert a["asset_id"] and a["revision_id"] and a["content_hash"]

        by_id = client.get(f"/api/v3/production/packages/{pkg['package_id']}")
        assert by_id.status_code == 200
        assert by_id.json()["package_hash"] == pkg["package_hash"]

    def test_refinalize_same_content_reuses_package(self, client):
        _prepare_ready_episode(client)
        first = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        ).json()["package"]

        second_resp = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        )
        assert second_resp.status_code == 200, "idempotent replay returns 200"
        second = second_resp.json()

        assert second["reused"] is True
        assert second["package"]["package_id"] == first["package_id"]
        history = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/packages").json()
        assert len(history) == 1, "no duplicate package record"

    def test_changed_target_creates_distinct_package(self, client):
        _prepare_ready_episode(client)
        a = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "BLENDER"},
        ).json()["package"]
        b = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "UNREAL"},
        ).json()["package"]
        assert a["package_id"] != b["package_id"]
        assert b["package_hash"] != a["package_hash"]

    def test_dependency_bump_does_not_mutate_old_package(self, client):
        """P1.6.5: Character v-next must leave the finalized package intact."""
        _prepare_ready_episode(client)
        pkg = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        ).json()["package"]

        # Mutate a dependency AFTER finalization (edit world bible name).
        wb = client.get(f"/api/v3/projects/{DEMO_PROJECT}/world").json()
        version = wb.get("version", 1)
        rr = client.patch(
            f"/api/v3/projects/{DEMO_PROJECT}/world",
            json={"world_name": "Neo-Saigon 2100", "expected_version": version},
        )
        assert rr.status_code == 200, rr.text

        after = client.get(f"/api/v3/production/packages/{pkg['package_id']}").json()
        assert after["package_hash"] == pkg["package_hash"], "old package immutable"
        assert after["world_canon"]["version"] == pkg["world_canon"]["version"]

    def test_shot_change_creates_new_package_keeps_old(self, client):
        """P1.6.6: new state → new package; Package A stays untouched."""
        _prepare_ready_episode(client)
        pkg_a = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        ).json()["package"]

        # Derive → edit a shot → re-pin → finalize again.
        r = client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/derive")
        assert r.status_code == 200, r.text
        shots = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/shots").json()
        target = shots[0]
        rr = client.patch(
            f"/api/v3/shots/{target['id']}",
            json={"duration_seconds": int(target["duration_seconds"]) + 0, "composition_notes": "v2 framing", "expected_version": target["version"]},
        )
        assert rr.status_code == 200, rr.text
        self._repin_after_edit(client)
        pkg_b = client.post(
            f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize",
            json={"production_target": "GENERIC_3D"},
        )

        assert pkg_b.status_code == 201, pkg_b.text
        pkg_b = pkg_b.json()["package"]
        assert pkg_b["package_id"] != pkg_a["package_id"]

        old = client.get(f"/api/v3/production/packages/{pkg_a['package_id']}").json()
        assert old["package_hash"] == pkg_a["package_hash"]
        assert old["shot_plan"]["revision_id"] == "sprev-ep-cb-001-v1", "old pin preserved"

        history = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/packages").json()
        assert [p["package_id"] for p in history] == [pkg_b["package_id"], pkg_a["package_id"]]

    @staticmethod
    def _repin_after_edit(client) -> None:
        """Re-stamp the derived draft's revision hash before pinning v2.

        The derive endpoint mints fresh DRAFT shots; pinning snapshots them,
        which is exactly the immutable handoff the package references.
        """
        r = client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")
        assert r.status_code == 200, r.text

    def test_get_unknown_package_404(self, client):
        r = client.get("/api/v3/production/packages/pkg-doesnotexist")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "PACKAGE_NOT_FOUND"
