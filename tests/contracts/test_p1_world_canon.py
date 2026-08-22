"""P1.2 — World Canon gate tests.

Gate: ``P1_2_WORLD_CANON_LIVE``

Covers the P1.2 plan sub-phases against the real API surface:

- Canonical World Bible fields (rule categories, visual/environment style,
  machine-checkable continuity constraints) with immutable pinned revisions
  and deterministic content hashes (plan §P1.2.1).
- Location production profiles (interior/exterior, day/night compatibility,
  architecture/lighting/palette, props, reusable set, continuity notes)
  (plan §P1.2.2).
- World Sync from the ACTUAL locked screenplay (plan §P1.2.4): fail-closed
  without a lock; ADD_LOCATION / UPDATE_PROPOSED / NO_CHANGE / CONFLICT;
  manual edits are never overwritten silently.
- Continuity checker (plan §P1.2.5): UNKNOWN_LOCATION,
  LOCATION_CONTINUITY_CONFLICT, WORLD_RULE_CONFLICT (only for
  machine-checkable rules), TIMELINE_CONFLICT; read-only, never mutating.

Tests self-provision through the public API and reuse the demo-seeded
Cyberpunk episode (StoryBible + ScreenplayDraft artifacts) by locking it.
The deterministic parser/checker edge cases are covered by direct unit calls
at the bottom of this module.
"""
from __future__ import annotations

import uuid

from windagent_api.services.world_canon_authority import (
    check_continuity,
    parse_scene_heading,
)


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


class TestCanonicalWorldBible:
    def test_initialize_carries_canonical_fields(self, client):
        proj = client.post("/api/v3/projects", json={"name": "Canon World Probe"})
        assert proj.status_code == 201, proj.text
        pid = proj.json()["id"]
        r = client.post(
            f"/api/v3/projects/{pid}/world/initialize",
            json={
                "world_name": "Thế Giới Thử Nghiệm",
                "setting_summary": "Một thành phố nổi trên biển.",
                "core_theme": "Kỷ luật vs tự do",
                "timeline_era": "Năm Hải Lịch 120",
                "physical_rules": ["Trọng lực thấp hơn 20% ban đêm"],
                "technology_rules": ["Mọi tàu thuyền chạy bằng năng lượng thủy triều"],
                "social_rules": ["Không ai sở hữu đất, chỉ thuê biển"],
                "visual_style": "Aquapunk pastel",
                "environment_style": "Biển mở, sương mù dày",
                "continuity_constraints": [
                    {"statement": "Không có súng hóa học", "forbidden_terms": ["súng ngắn", "khẩu súng"]},
                    "Luật văn chương thuần",
                ],
            },
        )
        assert r.status_code == 201, r.text
        wb = r.json()
        assert wb["world_name"] == "Thế Giới Thử Nghiệm"
        for field in (
            "physical_rules", "technology_rules", "magic_rules", "social_rules",
            "visual_style", "environment_style", "continuity_constraints",
            "content_hash", "current_revision_id",
        ):
            assert field in wb, f"canonical field '{field}' missing"
        assert wb["physical_rules"] == ["Trọng lực thấp hơn 20% ban đêm"]
        assert len(wb["content_hash"]) == 64
        assert wb["current_revision_id"] == f"wbrev-{wb['project_id']}-v{wb['version']}"

    def test_demo_project_world_has_canonical_defaults(self, client):
        wb = client.get("/api/v3/projects/proj-cyberpunk-01/world").json()
        for field in (
            "physical_rules", "technology_rules", "magic_rules", "social_rules",
            "visual_style", "environment_style", "continuity_constraints",
            "content_hash", "current_revision_id",
        ):
            assert field in wb, f"canonical field '{field}' missing"

    def test_update_pins_immutable_revision(self, client):
        wb = client.get("/api/v3/projects/proj-cyberpunk-01/world").json()
        old_hash = wb["content_hash"]
        r = client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"timeline_era": "Hậu Sụp Đổ 2071 — thời đại Apex", "expected_version": wb["version"]},
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["version"] == wb["version"] + 1
        assert updated["content_hash"] != old_hash

        revs = client.get("/api/v3/projects/proj-cyberpunk-01/world/revisions").json()
        versions = [rev["world_version"] for rev in revs]
        assert versions == sorted(versions), "revisions must be listed in order"
        assert versions[-1] == updated["version"]
        pinned = revs[-1]
        assert pinned["content_hash"] == updated["content_hash"]

        # Restore era so other tests keep a stable world state.
        client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"timeline_era": wb["timeline_era"], "expected_version": updated["version"]},
        )


class TestLocationProfile:
    def test_create_full_production_profile(self, client):
        r = client.post(
            "/api/v3/projects/proj-cyberpunk-01/world/locations",
            json={
                "name": "Chợ Đêm Tầng Trung",
                "type": "Exterior",
                "interior": False,
                "day_scene_compatible": True,
                "night_scene_compatible": True,
                "architecture": "Gian hàng mô-đun xếp lớp trên cầu vượt",
                "lighting_character": "Neon hồng xen huỳnh quang lạnh",
                "color_palette": ["hồng neon", "xanh điện", "cam sodium"],
                "important_props": ["quầy mì tự động", "màn hình giá rời"],
                "reusable_set": True,
                "continuity_notes": "Luôn ướt sau 22h vì hệ thống phun sương",
            },
        )
        assert r.status_code == 201, r.text
        loc = r.json()
        assert loc["reusable_set"] is True
        assert loc["exterior"] is True and loc["interior"] is False
        assert loc["color_palette"] == ["hồng neon", "xanh điện", "cam sodium"]
        assert len(loc["content_hash"]) == 64

    def test_update_profile_with_optimistic_lock(self, client):
        created = client.post(
            "/api/v3/projects/proj-cyberpunk-01/world/locations",
            json={"name": "Phòng Máy 12"},
        ).json()
        r = client.patch(
            f"/api/v3/projects/proj-cyberpunk-01/world/locations/{created['id']}",
            json={
                "night_scene_compatible": False,
                "lighting_character": "Đèn khẩn cấp đỏ",
                "expected_version": created["version"],
            },
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["night_scene_compatible"] is False
        assert updated["version"] == created["version"] + 1


class TestWorldSync:
    def test_sync_without_lock_fails_closed(self, client):
        r = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error_code"] == "SCREENPLAY_NOT_LOCKED"

    def test_sync_unknown_episode_404(self, client):
        r = client.post("/api/v3/episodes/ep-gate-missing/world/actions/canon-sync")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "EPISODE_NOT_FOUND"

    def test_sync_proposes_locations_and_apply_creates_them(self, client):
        lock_payload = _lock(client, "ep-cb-001")

        r = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync")
        assert r.status_code == 200, r.text
        proposal = r.json()
        assert proposal["status"] == "PROPOSED"
        assert proposal["domain"] == "world"
        assert proposal["lineage"]["source_screenplay_revision_id"] == lock_payload["revision_id"]

        names = {a["location_name"]: a for a in proposal["actions"]}
        assert "PHÒNG LÀM VIỆC CỦA ALEX" in names, proposal["actions"]
        assert names["PHÒNG LÀM VIỆC CỦA ALEX"]["action"] == "ADD_LOCATION"
        hem = names.get("HẺM TẦNG 404")
        assert hem is not None and hem["action"] == "ADD_LOCATION"

        # Apply the HẺM TẦNG 404 action -> canon location created with lineage.
        hem_index = next(i for i, a in enumerate(proposal["actions"]) if a["location_name"] == "HẺM TẦNG 404")
        apply_r = client.post(
            f"/api/v3/world-sync/{proposal['proposal_id']}/apply",
            json={"action_index": hem_index},
        )
        assert apply_r.status_code == 200, apply_r.text
        applied = apply_r.json()
        assert applied["applied_action"] == "ADD_LOCATION"
        loc = applied["location"]
        assert loc["name"] == "HẺM TẦNG 404"
        assert loc["interior"] is False and loc["exterior"] is True
        assert loc["last_synced_hash"], "sync baseline must be recorded"

        # Re-sync: applied location now matches -> NO_CHANGE, not duplicate.
        resync = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        resync_names = {a["location_name"]: a["action"] for a in resync["actions"]}
        assert resync_names["HẺM TẦNG 404"] == "NO_CHANGE"
        assert resync_names["PHÒNG LÀM VIỆC CỦA ALEX"] == "ADD_LOCATION"

    def test_manual_edit_becomes_conflict_never_overwritten(self, client):
        _lock(client, "ep-cb-001")
        proposal = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        hem_index = next(i for i, a in enumerate(proposal["actions"]) if a["location_name"] == "HẺM TẦNG 404")
        applied = client.post(
            f"/api/v3/world-sync/{proposal['proposal_id']}/apply",
            json={"action_index": hem_index},
        ).json()
        loc_id = applied["location"]["id"]

        # Manual edit AFTER the sync breaks the sync baseline...
        r = client.patch(
            f"/api/v3/projects/proj-cyberpunk-01/world/locations/{loc_id}",
            json={"description": "Mô tả riêng do người viết tay", "expected_version": applied["location"]["version"]},
        )
        assert r.status_code == 200, r.text

        # ...so the next sync must propose a CONFLICT, not an overwrite.
        resync = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        hem_action = next(a for a in resync["actions"] if a["location_name"] == "HẺM TẦNG 404")
        assert hem_action["action"] == "CONFLICT"

        conflict_index = resync["actions"].index(hem_action)
        apply_r = client.post(
            f"/api/v3/world-sync/{resync['proposal_id']}/apply",
            json={"action_index": conflict_index},
        )
        assert apply_r.status_code == 409
        assert apply_r.json()["detail"]["error_code"] == "ACTION_NOT_APPLICABLE"

        locations = client.get("/api/v3/projects/proj-cyberpunk-01/world/locations").json()
        assert next(loc for loc in locations if loc["id"] == loc_id)["description"] == (
            "Mô tả riêng do người viết tay"
        )

    def test_no_change_apply_refused(self, client):
        _lock(client, "ep-cb-001")
        first = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        hem_index = next(i for i, a in enumerate(first["actions"]) if a["location_name"] == "HẺM TẦNG 404")
        client.post(f"/api/v3/world-sync/{first['proposal_id']}/apply", json={"action_index": hem_index})
        second = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        no_change_index = next(i for i, a in enumerate(second["actions"]) if a["action"] == "NO_CHANGE")
        r = client.post(
            f"/api/v3/world-sync/{second['proposal_id']}/apply",
            json={"action_index": no_change_index},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error_code"] == "ACTION_NOT_APPLICABLE"

    def test_unknown_proposal_404(self, client):
        r = client.get("/api/v3/world-sync/wsync-gate-missing")
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "WORLD_PROPOSAL_NOT_FOUND"


class TestContinuityChecker:
    def test_check_without_lock_fails_closed(self, client):
        r = client.post("/api/v3/episodes/ep-cb-001/world/actions/continuity-check")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error_code"] == "SCREENPLAY_NOT_LOCKED"

    def test_unknown_locations_detected(self, client):
        _lock(client, "ep-cb-001")
        r = client.post("/api/v3/episodes/ep-cb-001/world/actions/continuity-check")
        assert r.status_code == 200, r.text
        result = r.json()
        types = [f["finding_type"] for f in result["findings"]]
        assert types.count("UNKNOWN_LOCATION") >= 2, result["findings"]
        unknown = next(f for f in result["findings"] if f["finding_type"] == "UNKNOWN_LOCATION")
        assert unknown["severity"] == "blocking"
        assert result["checked_screenplay_revision_id"], "must pin the locked revision"

    def test_night_incompatible_location_flagged(self, client):
        _lock(client, "ep-cb-001")
        proposal = client.post("/api/v3/episodes/ep-cb-001/world/actions/canon-sync").json()
        hem_index = next(i for i, a in enumerate(proposal["actions"]) if a["location_name"] == "HẺM TẦNG 404")
        applied = client.post(
            f"/api/v3/world-sync/{proposal['proposal_id']}/apply",
            json={"action_index": hem_index},
        ).json()

        # Scene 2 is a ĐÊM scene at HẺM TẦNG 404 — forbid night scenes there.
        r = client.patch(
            f"/api/v3/projects/proj-cyberpunk-01/world/locations/{applied['location']['id']}",
            json={"night_scene_compatible": False, "expected_version": applied["location"]["version"]},
        )
        assert r.status_code == 200, r.text

        result = client.post("/api/v3/episodes/ep-cb-001/world/actions/continuity-check").json()
        conflicts = [
            f for f in result["findings"]
            if f["finding_type"] == "LOCATION_CONTINUITY_CONFLICT"
        ]
        assert any("HẺM TẦNG 404" in f["message"] for f in conflicts), result["findings"]

    def test_machine_rule_conflict_detected(self, client):
        _lock(client, "ep-cb-001")
        wb = client.get("/api/v3/projects/proj-cyberpunk-01/world").json()
        r = client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={
                "continuity_constraints": [
                    {"statement": "Không ai nói về 'chuỗi mã' công khai", "forbidden_terms": ["chuỗi mã"]},
                ],
                "expected_version": wb["version"],
            },
        )
        assert r.status_code == 200, r.text

        result = client.post("/api/v3/episodes/ep-cb-001/world/actions/continuity-check").json()
        rule_conflicts = [
            f for f in result["findings"] if f["finding_type"] == "WORLD_RULE_CONFLICT"
        ]
        assert rule_conflicts, result["findings"]
        assert rule_conflicts[0]["severity"] == "blocking"
        assert rule_conflicts[0]["scene_number"] == 1

        # Restore the world bible so unrelated tests see the seeded rules.
        client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"continuity_constraints": [], "expected_version": r.json()["version"]},
        )

    def test_plain_text_rules_are_not_fabricated_as_conflicts(self, client):
        _lock(client, "ep-cb-001")
        wb = client.get("/api/v3/projects/proj-cyberpunk-01/world").json()
        r = client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={
                "continuity_constraints": ["Luật văn chương thuần không máy đọc được"],
                "expected_version": wb["version"],
            },
        )
        assert r.status_code == 200, r.text

        result = client.post("/api/v3/episodes/ep-cb-001/world/actions/continuity-check").json()
        assert not any(f["finding_type"] == "WORLD_RULE_CONFLICT" for f in result["findings"])
        unverified = [f for f in result["findings"] if f["finding_type"] == "UNVERIFIED_RULES"]
        assert unverified, "plain-text rules must be reported as needing human review, never guessed"

        client.patch(
            "/api/v3/projects/proj-cyberpunk-01/world",
            json={"continuity_constraints": [], "expected_version": r.json()["version"]},
        )


class TestDeterministicParserUnits:
    """Direct units for the heading grammar and checker edge cases."""

    def test_heading_parse_int_ext_and_times(self):
        parsed = parse_scene_heading("INT. PHÒNG LÀM VIỆC CỦA ALEX - ĐÊM")
        assert parsed == {
            "interior": True,
            "location_name": "PHÒNG LÀM VIỆC CỦA ALEX",
            "time_of_day": "NIGHT",
            "time_raw": "ĐÊM",
        }
        ext = parse_scene_heading("EXT. HẺM TẦNG 404 - ĐÊM")
        assert ext["interior"] is False
        day = parse_scene_heading("EXT. BẾN CẢNG - NGÀY")
        assert day["time_of_day"] == "DAY"
        both = parse_scene_heading("INT./EXT. CẦU TREO - NIGHT")
        assert both["interior"] is None

    def test_unparseable_heading_returns_none(self):
        assert parse_scene_heading("Cảnh mở màn ngoài trời") is None
        assert parse_scene_heading("") is None

    def test_timeline_conflict_detection(self):
        screenplay = {
            "content": {
                "scenes": [],
                "timeline_era": "Thời Đại Rồng Đỏ",
            }
        }
        world = {"timeline_era": "Năm Hải Lịch 120"}
        findings = check_continuity(screenplay, world, [])
        assert any(f["finding_type"] == "TIMELINE_CONFLICT" for f in findings)

    def test_matching_or_missing_timeline_is_silent(self):
        assert not [
            f for f in check_continuity(
                {"content": {"timeline_era": "Era X"}}, {"timeline_era": "era x"}, []
            )
            if f["finding_type"] == "TIMELINE_CONFLICT"
        ]
        # Missing data on either side must stay silent — never guessed.
        assert not [f for f in check_continuity({"content": {}}, {}, []) if f["finding_type"] == "TIMELINE_CONFLICT"]
