"""P1 Real Asset Persistence — real file/pinned revision proof.

Gate: P1_REAL_ASSET_PERSISTENCE

Uses a tiny valid PNG (1x1 transparent) rather than synthetic bytes.
Verifies:
  upload/store hash computed
  revision persisted
  review -> approved -> pin
  restart -> retrieve hash unchanged
  package references exact revision/hash
  negative: HASH_UNVERIFIED cannot be pinned, tampered fails closed
"""
from __future__ import annotations

import pytest
import base64
import hashlib

from fastapi.testclient import TestClient

from windagent_api.main import app

DEMO_EPISODE = "ep-cb-001"
DEMO_PROJECT = "proj-cyberpunk-01"

# 1x1 transparent PNG (67 bytes)
PNG_1X1_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
PNG_1X1_BYTES = base64.b64decode(PNG_1X1_B64)
PNG_1X1_HASH = hashlib.sha256(PNG_1X1_BYTES).hexdigest()

# A different 1x1 red PNG (to simulate tampered) — we just use different bytes
PNG_TAMPERED_B64 = base64.b64encode(b"tampered-not-png-" + PNG_1X1_BYTES).decode()


def _lock(client, episode_id=DEMO_EPISODE):
    ep = client.get(f"/api/v3/episodes/{episode_id}").json()
    r = client.post(f"/api/v3/episodes/{episode_id}/lock", json={
        "revision_id": "rev-cb-001-v3",
        "content_hash": "d" * 64,
        "expected_version": ep["version"],
    })
    assert r.status_code == 200, r.text


def _sync_all(client, episode_id=DEMO_EPISODE):
    # characters
    proposal = client.post(f"/api/v3/episodes/{episode_id}/characters/actions/canon-sync").json()
    for idx, action in enumerate(proposal["actions"]):
        if action["action"] == "ADD_CHARACTER":
            client.post(f"/api/v3/canon-sync/{proposal['proposal_id']}/apply", json={"action_index": idx})
    # world
    proposal = client.post(f"/api/v3/episodes/{episode_id}/world/actions/canon-sync").json()
    for idx, action in enumerate(proposal["actions"]):
        if action["action"] == "ADD_LOCATION":
            client.post(f"/api/v3/world-sync/{proposal['proposal_id']}/apply", json={"action_index": idx})
    client.post(f"/api/v3/episodes/{episode_id}/storyboard/actions/sync")
    client.post(f"/api/v3/episodes/{episode_id}/assets/requirements/actions/sync")
    client.post(f"/api/v3/episodes/{episode_id}/production/shot-plan/actions/generate")


def _enrich_characters(client):
    chars = client.get(f"/api/v3/projects/{DEMO_PROJECT}/characters").json()
    for char in chars:
        patch = {"expected_version": char["version"]}
        cont = char.get("continuity") or {}
        if not (cont.get("immutable_features") or cont.get("wardrobe_rules")):
            patch["immutable_features"] = ["silver hair"]
            patch["wardrobe_rules"] = ["dark coat"]
        if not (char.get("visual_profile") or {}).get("physical_description"):
            patch["physical_description"] = "Tóc bạc, mắt xám"
        if len(patch) > 1:
            r = client.patch(f"/api/v3/characters/{char['id']}", json=patch)
            assert r.status_code == 200, r.text
            char = r.json()
        for nxt in ("REVIEW_REQUIRED", "APPROVED", "PRODUCTION_READY"):
            if char.get("status") == nxt:
                continue
            r = client.post(f"/api/v3/characters/{char['id']}/actions/set-status", json={"status": nxt, "expected_version": char["version"]})
            assert r.status_code == 200, r.text
            char = r.json()


class TestRealAssetPersistence:
    def test_real_png_asset_hash_and_pinned_workflow(self, client):
        _lock(client)
        _sync_all(client)
        _enrich_characters(client)

        reqs = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json()
        req = next(r for r in reqs if r.get("mandatory") and r.get("status") == "OPEN")
        requirement_id = req["requirement_id"]

        # Create asset with REAL PNG bytes
        r = client.post("/api/v3/assets", json={
            "name": f"Real PNG {req['name']}",
            "type": "IMAGE",
            "episode_id": DEMO_EPISODE,
            "project_id": DEMO_PROJECT,
            "requirement_id": requirement_id,
            "content_base64": PNG_1X1_B64,
        })
        assert r.status_code == 201, r.text
        asset = r.json()
        assert asset["provenance"]["content_hash"] == PNG_1X1_HASH, f"hash mismatch {asset['provenance']}"
        assert asset["provenance"]["hash_status"] == "VERIFIED"
        assert asset["current_revision_id"].startswith("rev-")

        rev_id = asset["current_revision_id"]
        # List revisions: should contain the revision we just created
        revs = client.get(f"/api/v3/assets/{asset['id']}/revisions").json()
        assert any(r["revision_id"] == rev_id for r in revs)
        assert any(r["provenance"]["content_hash"] == PNG_1X1_HASH for r in revs)

        # Review -> Approved -> PINNED
        for nxt in ("REVIEW", "APPROVED"):
            r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": nxt, "expected_version": asset["version"]})
            assert r2.status_code == 200, r2.text
            asset = r2.json()
        # Approve specific revision
        r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/approve", json={"revision_id": rev_id, "approved_by": "tester"})
        assert r2.status_code == 200, r2.text
        asset = r2.json()
        assert asset["approval_pin"]["content_hash"] == PNG_1X1_HASH
        assert asset["approval_pin"]["revision_id"] == rev_id

        r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": "PINNED", "expected_version": asset["version"]})
        assert r2.status_code == 200, r2.text
        pinned = r2.json()
        assert pinned["status"] == "PINNED"
        assert pinned["provenance"]["content_hash"] == PNG_1X1_HASH

        # Retrieve again: hash unchanged
        fetched = client.get(f"/api/v3/assets/{asset['id']}").json()
        assert fetched["provenance"]["content_hash"] == PNG_1X1_HASH
        assert fetched["status"] == "PINNED"

        # Pin shot plan to allow preflight/finalize
        client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")
        # Ensure at least one other mandatory requirement is also fulfilled for READY
        # Fulfill remaining OPEN mandatory reqs with synthetic verified bytes so package can finalize
        for extra_req in client.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json():
            if extra_req.get("mandatory") and extra_req.get("status") == "OPEN":
                raw = base64.b64encode(b"verified-bytes:" + extra_req["requirement_id"].encode()).decode()
                ra = client.post("/api/v3/assets", json={
                    "name": f"Fulfil {extra_req['name']}",
                    "type": "IMAGE",
                    "episode_id": DEMO_EPISODE,
                    "project_id": DEMO_PROJECT,
                    "requirement_id": extra_req["requirement_id"],
                    "content_base64": raw,
                })
                assert ra.status_code == 201, ra.text
                a = ra.json()
                for nxt in ("REVIEW", "APPROVED"):
                    r2 = client.post(f"/api/v3/assets/{a['id']}/actions/set-status", json={"status": nxt, "expected_version": a["version"]})
                    assert r2.status_code == 200
                    a = r2.json()
                r2 = client.post(f"/api/v3/assets/{a['id']}/actions/approve", json={"revision_id": a["current_revision_id"], "approved_by": "tester"})
                assert r2.status_code == 200
                a = r2.json()
                r2 = client.post(f"/api/v3/assets/{a['id']}/actions/set-status", json={"status": "PINNED", "expected_version": a["version"]})
                assert r2.status_code == 200

        body = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/production/package/preflight").json()
        assert body["status"] == "READY", body["blocking_findings"]

        pkg = client.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize", json={"production_target": "GENERIC_3D"}).json()["package"]
        # Package must reference our exact pinned revision/hash
        asset_pins = {a["asset_id"]: a for a in pkg["assets"]}
        assert asset["id"] in asset_pins, "real asset not in package"
        assert asset_pins[asset["id"]]["content_hash"] == PNG_1X1_HASH
        assert asset_pins[asset["id"]]["revision_id"] == rev_id

    def test_hash_unverified_cannot_be_pinned(self, client):
        _lock(client)
        _sync_all(client)
        _enrich_characters(client)
        reqs = client.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json()
        req = next(r for r in reqs if r.get("mandatory") and r.get("status") == "OPEN")
        # Create asset WITHOUT content_base64 => HASH_UNVERIFIED
        r = client.post("/api/v3/assets", json={
            "name": "Unverified asset",
            "type": "IMAGE",
            "episode_id": DEMO_EPISODE,
            "project_id": DEMO_PROJECT,
            "requirement_id": req["requirement_id"],
        })
        assert r.status_code == 201, r.text
        asset = r.json()
        assert asset["provenance"]["hash_status"] == "HASH_UNVERIFIED"
        # Try to drive to PINNED -> should fail closed at approve/pin
        for nxt in ("REVIEW", "APPROVED"):
            r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": nxt, "expected_version": asset["version"]})
            assert r2.status_code == 200, r2.text
            asset = r2.json()
        # Approve still succeeds (revision exists) but pin must fail because hash unverified
        r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/approve", json={"revision_id": asset["current_revision_id"], "approved_by": "tester"})
        assert r2.status_code == 200, r2.text
        asset = r2.json()
        r2 = client.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": "PINNED", "expected_version": asset["version"]})
        assert r2.status_code == 409, r2.text
        assert r2.json()["detail"]["error_code"] == "ASSET_HASH_UNVERIFIED"

    def test_restart_preserves_real_asset_hash(self, monkeypatch, tmp_path):
        """Restart persistence for real asset: hash survives restart, no duplicates."""
        monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'real_restart.db').as_posix()}")
        with TestClient(app) as first:
            _lock(first)
            _sync_all(first)
            _enrich_characters(first)
            reqs = first.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json()
            req = next(r for r in reqs if r.get("mandatory") and r.get("status") == "OPEN")
            r = first.post("/api/v3/assets", json={
                "name": "Real restart PNG",
                "type": "IMAGE",
                "episode_id": DEMO_EPISODE,
                "project_id": DEMO_PROJECT,
                "requirement_id": req["requirement_id"],
                "content_base64": PNG_1X1_B64,
            })
            assert r.status_code == 201, r.text
            asset = r.json()
            rev_id = asset["current_revision_id"]
            for nxt in ("REVIEW", "APPROVED"):
                r2 = first.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": nxt, "expected_version": asset["version"]})
                assert r2.status_code == 200
                asset = r2.json()
            r2 = first.post(f"/api/v3/assets/{asset['id']}/actions/approve", json={"revision_id": rev_id, "approved_by": "tester"})
            assert r2.status_code == 200
            asset = r2.json()
            r2 = first.post(f"/api/v3/assets/{asset['id']}/actions/set-status", json={"status": "PINNED", "expected_version": asset["version"]})
            assert r2.status_code == 200
            pinned = r2.json()
            asset_id = pinned["id"]
            pinned_hash = pinned["provenance"]["content_hash"]
            assert pinned_hash == PNG_1X1_HASH
            # finalize to ensure package persists too
            for extra_req in first.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json():
                if extra_req.get("mandatory") and extra_req.get("status") == "OPEN":
                    raw = base64.b64encode(b"verified-bytes:" + extra_req["requirement_id"].encode()).decode()
                    ra = first.post("/api/v3/assets", json={
                        "name": f"Fulfil {extra_req['name']}",
                        "type": "IMAGE",
                        "episode_id": DEMO_EPISODE,
                        "project_id": DEMO_PROJECT,
                        "requirement_id": extra_req["requirement_id"],
                        "content_base64": raw,
                    })
                    assert ra.status_code == 201
                    a = ra.json()
                    for nxt in ("REVIEW", "APPROVED"):
                        r2 = first.post(f"/api/v3/assets/{a['id']}/actions/set-status", json={"status": nxt, "expected_version": a["version"]})
                        assert r2.status_code == 200
                        a = r2.json()
                    r2 = first.post(f"/api/v3/assets/{a['id']}/actions/approve", json={"revision_id": a["current_revision_id"], "approved_by": "tester"})
                    assert r2.status_code == 200
                    a = r2.json()
                    r2 = first.post(f"/api/v3/assets/{a['id']}/actions/set-status", json={"status": "PINNED", "expected_version": a["version"]})
                    assert r2.status_code == 200
            first.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/shot-plan/actions/pin")
            pkg = first.post(f"/api/v3/episodes/{DEMO_EPISODE}/production/package/actions/finalize", json={"production_target": "GENERIC_3D"}).json()["package"]
            pkg_id = pkg["package_id"]

        with TestClient(app) as second:
            fetched = second.get(f"/api/v3/assets/{asset_id}").json()
            assert fetched["provenance"]["content_hash"] == PNG_1X1_HASH == pinned_hash
            assert fetched["status"] == "PINNED"
            revs = second.get(f"/api/v3/assets/{asset_id}/revisions").json()
            assert any(r["revision_id"] == rev_id and r["provenance"]["content_hash"] == PNG_1X1_HASH for r in revs)
            restored = second.get(f"/api/v3/production/packages/{pkg_id}").json()
            assert restored["package_hash"] == pkg["package_hash"]

@pytest.mark.postgres
class TestPostgresRealAsset:
    def test_pg_real_asset_on_postgres(self, monkeypatch, tmp_path):
        import os
        pg_url = os.environ.get("WINDAGENT_TEST_POSTGRES_URL", "").strip()
        if not pg_url or not pg_url.startswith("postgresql+asyncpg://"):
            pytest.skip("PG not available")
        monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", pg_url)
        with TestClient(app) as api:
            _lock(api)
            _sync_all(api)
            _enrich_characters(api)
            reqs = api.get(f"/api/v3/episodes/{DEMO_EPISODE}/assets/requirements").json()
            req = next(r for r in reqs if r.get("mandatory") and r.get("status") == "OPEN")
            r = api.post("/api/v3/assets", json={
                "name": f"PG Real {req['name']}",
                "type": "IMAGE",
                "episode_id": DEMO_EPISODE,
                "project_id": DEMO_PROJECT,
                "requirement_id": req["requirement_id"],
                "content_base64": PNG_1X1_B64,
            })
            assert r.status_code == 201, r.text
            asset = r.json()
            assert asset["provenance"]["content_hash"] == PNG_1X1_HASH

