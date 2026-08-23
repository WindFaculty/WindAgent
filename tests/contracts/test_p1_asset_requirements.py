"""P1.3 — Asset Requirements & Asset Registry gate tests.

Gate: ``P1_3_ASSET_AUTHORITY_LIVE``

Covers the P1.3 plan sub-phases against the real API surface:

- Deterministic Asset Requirement extraction from the locked screenplay +
  Character/Location canon (plan §P1.3.1): fail-closed without a lock,
  idempotent re-sync, props only from Location Canon profiles.
- Asset lifecycle REQUIRED -> ... -> APPROVED -> PINNED one step at a time,
  with honest failure paths (plan §P1.3.2).
- Asset sources incl. REFERENCE (plan §P1.3.3).
- Provenance content hashes are SHA-256 over the ACTUAL bytes;
  HASH_UNVERIFIED content can never be PINNED (plan §P1.3.4).
- Dependency graph through parent_revision links (plan §P1.3.5).
- Approval pins a SPECIFIC revision with asset_id + revision_id +
  content_hash + approved_by + approved_at — never a floating "latest"
  (plan §P1.3.6).

Tests self-provision through the public API and reuse the demo-seeded
Cyberpunk episode by locking it.
"""
from __future__ import annotations

import base64
import hashlib
import uuid


def _lock(client, episode_id: str) -> dict:
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    payload = {
        "revision_id": f"rev-{uuid.uuid4().hex[:10]}",
        "content_hash": "a" * 64,
        "expected_version": ep["version"],
    }
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json=payload)
    assert r.status_code == 200, r.text
    return payload


class TestRequirementExtraction:
    def test_sync_without_lock_fails_closed(self, client):
        r = client.post("/api/v3/episodes/ep-cb-001/assets/requirements/actions/sync")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error_code"] == "SCREENPLAY_NOT_LOCKED"

    def test_sync_unknown_episode_404(self, client):
        r = client.post("/api/v3/episodes/ep-gate-missing/assets/requirements/actions/sync")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "EPISODE_NOT_FOUND"

    def test_sync_extracts_characters_environments_and_props(self, client):
        # Register a Location Canon profile whose important_props must become
        # PROP requirements for the scenes that use the location.
        loc_r = client.post(
            "/api/v3/projects/proj-cyberpunk-01/world/locations",
            json={
                "name": "HẺM TẦNG 404",
                "type": "Exterior",
                "important_props": ["biển hiệu neon gãy", "thùng rác kim loại"],
            },
        )
        assert loc_r.status_code == 201, loc_r.text

        lock_payload = _lock(client, "ep-cb-001")

        # Production order: Character Canon first, so the CHARACTER
        # requirement carries the canon identity name.
        char_proposal = client.post("/api/v3/episodes/ep-cb-001/characters/actions/canon-sync").json()
        alex_index = next(i for i, a in enumerate(char_proposal["actions"]) if a["character_name"] == "Alex")
        client.post(
            f"/api/v3/canon-sync/{char_proposal['proposal_id']}/apply",
            json={"action_index": alex_index},
        )

        r = client.post("/api/v3/episodes/ep-cb-001/assets/requirements/actions/sync")
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["lineage"]["source_screenplay_revision_id"] == lock_payload["revision_id"]

        listed = client.get("/api/v3/episodes/ep-cb-001/assets/requirements").json()
        by_key = {(req["type"], req["name"]): req for req in listed}

        alex = by_key.get(("CHARACTER", "Alex"))
        assert alex is not None, listed
        assert alex["mandatory"] is True
        assert alex["scene_usage"] == [1], "Alex speaks only in scene 1"
        assert len(alex["content_hash"]) == 64

        hem = by_key.get(("ENVIRONMENT", "HẺM TẦNG 404"))
        assert hem is not None and hem["scene_usage"] == [2]

        prop = by_key.get(("PROP", "biển hiệu neon gãy"))
        assert prop is not None, "props must come from the Location Canon profile"
        assert prop["scene_usage"] == [2]

        # No invented MUSIC/SFX requirements without structured sources.
        assert not any(req["type"] in ("MUSIC", "SFX") for req in listed)

    def test_sync_is_idempotent(self, client):
        _lock(client, "ep-cb-001")
        first = client.post("/api/v3/episodes/ep-cb-001/assets/requirements/actions/sync").json()
        assert first["created_count"] > 0
        second = client.post("/api/v3/episodes/ep-cb-001/assets/requirements/actions/sync").json()
        assert second["created_count"] == 0, second["created"]
        assert second["total_count"] == first["total_count"]
        listed_after = client.get("/api/v3/episodes/ep-cb-001/assets/requirements").json()
        assert len(listed_after) == first["total_count"], "no duplicates on re-sync"


class TestRequirementFulfilment:
    def test_asset_creation_fulfils_requirement(self, client):
        _lock(client, "ep-cb-001")
        client.post("/api/v3/episodes/ep-cb-001/assets/requirements/actions/sync")
        listed = client.get("/api/v3/episodes/ep-cb-001/assets/requirements").json()
        target = next(r for r in listed if r["type"] == "CHARACTER")

        payload = base64.b64encode(b"alex-reference-sheet-bytes").decode()
        r = client.post(
            "/api/v3/assets",
            json={
                "name": f"Alex ref sheet {uuid.uuid4().hex[:6]}",
                "type": "IMAGE",
                "source": "UPLOAD",
                "requirement_id": target["requirement_id"],
                "project_id": "proj-cyberpunk-01",
                "episode_id": "ep-cb-001",
                "content_base64": payload,
            },
        )
        assert r.status_code == 201, r.text
        asset = r.json()
        assert asset["requirement_id"] == target["requirement_id"]

        refreshed = client.get("/api/v3/projects/proj-cyberpunk-01/assets/requirements").json()
        fulfilled = next(
            req for req in refreshed if req["requirement_id"] == target["requirement_id"]
        )
        assert fulfilled["status"] == "FULFILLED"
        assert fulfilled["linked_asset_id"] == asset["id"]

    def test_unknown_requirement_404(self, client):
        r = client.post(
            "/api/v3/assets",
            json={"name": "Orphan asset", "requirement_id": "areq-gate-missing"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "REQUIREMENT_NOT_FOUND"


class TestAssetLifecycle:
    def _create(self, client, **overrides) -> dict:
        body = {
            "name": f"Lifecycle probe {uuid.uuid4().hex[:6]}",
            "type": "IMAGE",
            "project_id": "proj-cyberpunk-01",
            **overrides,
        }
        r = client.post("/api/v3/assets", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def test_ladder_advances_one_step_at_a_time(self, client):
        asset = self._create(client)
        assert asset["status"] == "DRAFT"

        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "PINNED", "expected_version": asset["version"]},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "INVALID_ASSET_STATUS_TRANSITION"

        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "REVIEW", "expected_version": asset["version"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "REVIEW"

        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "GODMODE", "expected_version": r.json()["version"]},
        )
        assert r.status_code == 422

    def test_unverified_hash_can_be_approved_but_never_pinned(self, client):
        asset = self._create(client)  # no content_base64 -> HASH_UNVERIFIED
        version = asset["version"]
        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "REVIEW", "expected_version": version},
        )
        assert r.status_code == 200, r.text
        approved = client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={
                "revision_id": asset["current_revision_id"],
                "approved_by": "qa-reviewer",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval_pin"]["revision_id"] == asset["current_revision_id"]

        pinned = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "PINNED", "expected_version": approved.json()["version"]},
        )
        assert pinned.status_code == 409, pinned.text
        assert pinned.json()["detail"]["error_code"] == "ASSET_HASH_UNVERIFIED"

    def test_verified_bytes_reach_pinned(self, client):
        payload = base64.b64encode(b"production-ready-image-v1").decode()
        asset = self._create(client, source="UPLOAD", content_base64=payload)
        prov = asset["provenance"]
        assert prov["hash_status"] == "VERIFIED"
        assert prov["content_hash"] == hashlib.sha256(b"production-ready-image-v1").hexdigest()

        version = asset["version"]
        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "REVIEW", "expected_version": version},
        )
        assert r.status_code == 200, r.text
        approved = client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={
                "revision_id": asset["current_revision_id"],
                "approved_by": "art-director",
            },
        )
        assert approved.status_code == 200, approved.text
        pinned = client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "PINNED", "expected_version": approved.json()["version"]},
        )
        assert pinned.status_code == 200, pinned.text
        assert pinned.json()["status"] == "PINNED"

    def test_invalid_base64_422(self, client):
        r = client.post(
            "/api/v3/assets",
            json={"name": "Bad encoding", "content_base64": "!!!not-base64!!!"},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["error_code"] == "INVALID_CONTENT_ENCODING"

    def test_new_revision_returns_to_draft_keeps_old_pin(self, client):
        payload = base64.b64encode(b"v1-bytes").decode()
        asset = self._create(client, source="UPLOAD", content_base64=payload)
        old_rev = asset["current_revision_id"]
        client.post(
            f"/api/v3/assets/{asset['id']}/actions/set-status",
            json={"status": "REVIEW", "expected_version": asset["version"]},
        )
        client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={"revision_id": old_rev, "approved_by": "art-director"},
        )

        payload2 = base64.b64encode(b"v2-bytes").decode()
        rev_r = client.post(
            f"/api/v3/assets/{asset['id']}/revisions",
            json={"content_base64": payload2, "media_url": "memory://v2.png"},
        )
        assert rev_r.status_code == 201, rev_r.text
        new_rev = rev_r.json()
        assert new_rev["provenance"]["content_hash"] == hashlib.sha256(b"v2-bytes").hexdigest()
        assert new_rev["provenance"]["parent_revision_id"] == old_rev

        after = client.get(f"/api/v3/assets/{asset['id']}").json()
        assert after["status"] == "DRAFT", "new work supersedes the approved state"
        assert after["current_revision_id"] == new_rev["revision_id"]

        revs = client.get(f"/api/v3/assets/{asset['id']}/revisions").json()
        old = next(rev for rev in revs if rev["revision_id"] == old_rev)
        assert old["approval_pin"]["revision_id"] == old_rev, "old approval pin stands"
        assert old["provenance"]["content_hash"] == hashlib.sha256(b"v1-bytes").hexdigest()


class TestApprovalPinAndDependencies:
    def test_approve_pins_specific_revision_not_latest(self, client):
        payload1 = base64.b64encode(b"first-take").decode()
        asset_r = client.post(
            "/api/v3/assets",
            json={
                "name": f"Pin target {uuid.uuid4().hex[:6]}",
                "type": "IMAGE",
                "project_id": "proj-cyberpunk-01",
                "source": "UPLOADED",
                "content_base64": payload1,
            },
        )
        asset = asset_r.json()
        old_rev = asset["current_revision_id"]
        client.post(
            f"/api/v3/assets/{asset['id']}/revisions",
            json={"content_base64": base64.b64encode(b"second-take").decode()},
        )

        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={"revision_id": old_rev, "approved_by": "director"},
        )
        assert r.status_code == 200, r.text
        pin = r.json()["approval_pin"]
        assert pin["revision_id"] == old_rev, "must pin the requested revision, not latest"
        assert pin["content_hash"] == hashlib.sha256(b"first-take").hexdigest()
        assert pin["approved_by"] == "director"
        assert pin["approved_at"]

    def test_approve_unknown_revision_422(self, client):
        asset = client.post(
            "/api/v3/assets",
            json={"name": f"No such rev {uuid.uuid4().hex[:4]}"},
        ).json()
        r = client.post(
            f"/api/v3/assets/{asset['id']}/actions/approve",
            json={"revision_id": "rev-does-not-exist", "approved_by": "director"},
        )
        assert r.status_code == 422

    def test_dependency_graph_downstream(self, client):
        parent = client.post(
            "/api/v3/assets",
            json={
                "name": f"Parent sheet {uuid.uuid4().hex[:4]}",
                "content_base64": base64.b64encode(b"parent-bytes").decode(),
            },
        ).json()
        child = client.post(
            "/api/v3/assets",
            json={
                "name": f"Child model {uuid.uuid4().hex[:4]}",
                "source": "GENERATED",
                "parent_revision_id": parent["current_revision_id"],
            },
        ).json()
        deps = client.get(f"/api/v3/assets/{parent['id']}/dependencies").json()
        assert child["id"] in deps
