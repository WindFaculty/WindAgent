"""
Comprehensive Test Suite for Stage G — Offline, Recovery & Conflict Handling (UI39 & UI40).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app
from windagent_core.domain.video_production.state_recovery import (
    create_recovery_snapshot,
)
from windagent_core.domain.video_production.conflict_resolution_service import (
    ConflictResolutionService,
    ConflictResolutionPayload,
    ResolutionStrategy,
    ThreeWayDiffEngine,
    ConflictClassification,
)


@pytest.fixture(autouse=True)
def reset_stores():
    ConflictResolutionService.clear_store()


def test_snapshot_checksum_validation_and_sanitization():
    raw_units = {
        "text": "Unsaved screenplay text edit",
        "api_key": "sk-1234567890abcdef1234",
        "access_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
        "file_path": "C:\\Users\\Admin\\AppData\\Local\\Temp\\secret.fountain",
    }

    snapshot = create_recovery_snapshot(
        saved_at="2026-08-08T15:00:00Z",
        project_id="proj_g_01",
        revision_id="rev_01",
        base_sequence=1,
        edit_units=raw_units,
    )

    # 1. Verify Checksum matches
    assert snapshot.validate_checksum() is True

    # 2. Tamper snapshot
    snapshot.edit_units["text"] = "TAMPERED TEXT"
    assert snapshot.validate_checksum() is False

    # 3. Verify Sanitizer redacts tokens and paths
    sanitized = snapshot.sanitize()
    units = sanitized.edit_units
    assert "sk-1234567890abcdef1234" not in str(units)
    assert "[REDACTED_SECRET]" in units["api_key"]
    assert "[REDACTED_LOCAL_PATH]" in units["file_path"] or "[REDACTED_SECRET]" in units["file_path"]


def test_three_way_diff_classification_local_only():
    base_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [{"dialogue_id": "d_01", "character_name": "ALICE", "text": "Hello"}],
            }
        ],
    }

    local_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1 - POLISHED",
                "order": 1,
                "dialogue_lines": [{"dialogue_id": "d_01", "character_name": "ALICE", "text": "Hello world!"}],
            }
        ],
    }

    remote_model = base_model  # No changes on remote

    result = ThreeWayDiffEngine.compare("proj_g_02", base_model, local_model, remote_model)

    assert result.overall_classification == ConflictClassification.LOCAL_ONLY_CHANGE
    assert result.can_auto_merge is True
    assert len(result.entity_conflicts) == 2  # Scene and dialogue


def test_three_way_diff_non_overlapping_mergeable():
    base_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [
                    {"dialogue_id": "d_01", "character_name": "ALICE", "text": "Line 1"},
                    {"dialogue_id": "d_02", "character_name": "BOB", "text": "Line 2"},
                ],
            }
        ],
    }

    # Local edits Line 1
    local_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [
                    {"dialogue_id": "d_01", "character_name": "ALICE", "text": "Line 1 - LOCAL MODIFIED"},
                    {"dialogue_id": "d_02", "character_name": "BOB", "text": "Line 2"},
                ],
            }
        ],
    }

    # Remote edits Line 2
    remote_model = {
        "revision_id": "rev_02",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [
                    {"dialogue_id": "d_01", "character_name": "ALICE", "text": "Line 1"},
                    {"dialogue_id": "d_02", "character_name": "BOB", "text": "Line 2 - REMOTE MODIFIED"},
                ],
            }
        ],
    }

    result = ThreeWayDiffEngine.compare("proj_g_03", base_model, local_model, remote_model)

    assert result.overall_classification == ConflictClassification.NON_OVERLAPPING_MERGEABLE
    assert result.can_auto_merge is True
    assert result.auto_merged_payload is not None

    # Check that merged payload contains both Line 1 local edit and Line 2 remote edit
    merged_scene = result.auto_merged_payload["scenes"][0]
    dlgs = {d["dialogue_id"]: d["text"] for d in merged_scene["dialogue_lines"]}
    assert dlgs["d_01"] == "Line 1 - LOCAL MODIFIED"
    assert dlgs["d_02"] == "Line 2 - REMOTE MODIFIED"


def test_three_way_diff_overlapping_requires_review():
    base_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [{"dialogue_id": "d_01", "character_name": "ALICE", "text": "Original text"}],
            }
        ],
    }

    local_model = {
        "revision_id": "rev_01",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [{"dialogue_id": "d_01", "character_name": "ALICE", "text": "Local text change"}],
            }
        ],
    }

    remote_model = {
        "revision_id": "rev_02",
        "title": "Base Title",
        "scenes": [
            {
                "scene_id": "sc_01",
                "title": "SCENE 1",
                "order": 1,
                "dialogue_lines": [{"dialogue_id": "d_01", "character_name": "ALICE", "text": "Remote text change"}],
            }
        ],
    }

    result = ThreeWayDiffEngine.compare("proj_g_04", base_model, local_model, remote_model)

    assert result.overall_classification == ConflictClassification.OVERLAPPING_REQUIRES_REVIEW
    assert result.can_auto_merge is False
    assert result.auto_merged_payload is None


def test_conflict_resolution_strategies():
    base_model = {"revision_id": "rev_01", "title": "Base", "scenes": []}
    remote_model = {"revision_id": "rev_02", "title": "Remote", "scenes": []}

    ConflictResolutionService.register_revision("rev_01", base_model)
    ConflictResolutionService.register_revision("rev_02", remote_model)

    # Strategy 1: ACCEPT_REMOTE
    payload_remote = ConflictResolutionPayload(
        project_id="proj_g_05",
        base_revision_id="rev_01",
        latest_revision_id="rev_02",
        strategy=ResolutionStrategy.ACCEPT_REMOTE,
        resolved_by="user:director",
    )

    res_remote = ConflictResolutionService.resolve_conflict(payload_remote)
    assert res_remote["strategy"] == "ACCEPT_REMOTE"
    assert res_remote["resulting_revision_id"].startswith("rev_resolved_")
    assert res_remote["resolved_payload"]["title"] == "Remote"

    # Strategy 2: ACCEPT_LOCAL
    local_custom = {"revision_id": "rev_local", "title": "Local Custom", "scenes": []}
    payload_local = ConflictResolutionPayload(
        project_id="proj_g_05",
        base_revision_id="rev_01",
        latest_revision_id="rev_02",
        strategy=ResolutionStrategy.ACCEPT_LOCAL,
        custom_screenplay_payload=local_custom,
        resolved_by="user:editor",
    )

    res_local = ConflictResolutionService.resolve_conflict(payload_local)
    assert res_local["strategy"] == "ACCEPT_LOCAL"
    assert res_local["resolved_payload"]["title"] == "Local Custom"


def test_api_v2_recovery_reconcile_and_conflict():
    """Phase 15: the V2 recovery/conflict HTTP surface is retired (410).

    The ConflictResolutionService / recovery domain logic above remains
    canonical; the retired /api/v2/recovery|conflict routes are pinned here.
    """
    client = TestClient(app)

    resp_reconcile = client.get("/api/v2/recovery/reconcile?project_id=proj_api_g&client_base_revision_id=rev_01&client_base_sequence=1")
    assert resp_reconcile.status_code == 410
    assert resp_reconcile.json()["title"] == "API V2 Retired"

    resp_stale = client.post("/api/v2/conflict/check-stale-edit?project_id=proj_api_g&client_base_revision_id=rev_stale_old&server_latest_revision_id=rev_02")
    assert resp_stale.status_code == 410

    diff_payload = {
        "project_id": "proj_api_g",
        "base_revision_id": "rev_01",
        "local_payload": {"revision_id": "rev_01", "title": "Local Title", "scenes": []},
        "latest_revision_id": "rev_02",
        "latest_payload": {"revision_id": "rev_02", "title": "Remote Title", "scenes": []},
    }
    resp_diff = client.post("/api/v2/conflict/three-way-diff", json=diff_payload)
    assert resp_diff.status_code == 410

    resolve_payload = {
        "project_id": "proj_api_g",
        "base_revision_id": "rev_01",
        "latest_revision_id": "rev_02",
        "strategy": "ACCEPT_REMOTE",
        "resolved_by": "user:test_runner",
    }
    resp_resolve = client.post("/api/v2/conflict/resolve", json=resolve_payload)
    assert resp_resolve.status_code == 410
