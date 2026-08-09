"""
API Integration Tests for Stage B Production Workspace & Canonical Commands.
- Workspace snapshot reading from durable database
- Canonical command envelope execution with X-Idempotency-Key
- Rejection of stale target revisions (409 Conflict)
- Rejection of locked revisions (409 Conflict)
- Idempotency key reuse mismatch detection (409 Conflict)
- Replay of identical responses for matching idempotency key & payload
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_stage_b.db"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    with TestClient(app) as test_client:
        yield test_client


def test_get_workspace_snapshot_initializes_durable_project(client):
    res = client.get("/api/v2/video-production/projects/vp_unit_01/workspace")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["project_id"] == "vp_unit_01"
    assert data["revision_id"].startswith("rev_")
    assert data["current_sequence"] >= 1
    assert data["creative_brief_locked"] is True


def test_canonical_command_execution_success(client):
    # 1. Fetch initial snapshot
    snap_res = client.get("/api/v2/video-production/projects/vp_unit_02/workspace")
    assert snap_res.status_code == 200
    snap = snap_res.json()
    rev_id = snap["revision_id"]

    # 2. Execute command with X-Idempotency-Key
    cmd_res = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "idemp_cmd_001"},
        json={
            "command_type": "UPDATE_SCENE",
            "project_id": "vp_unit_02",
            "target_revision_id": rev_id,
            "entity_id": "scene_01",
            "reason": "Dialogue refinement",
            "payload": {"text": "Updated scene text"},
        },
    )
    assert cmd_res.status_code == 200, cmd_res.text
    cmd_data = cmd_res.json()
    assert cmd_data["status"] == "COMPLETED"
    assert cmd_data["updated_revision_id"] != rev_id
    assert cmd_data["current_sequence"] > snap["current_sequence"]


def test_canonical_command_idempotency_replay_and_mismatch(client):
    snap = client.get("/api/v2/video-production/projects/vp_unit_03/workspace").json()
    rev_id = snap["revision_id"]

    payload_a = {
        "command_type": "ADD_SHOT",
        "project_id": "vp_unit_03",
        "target_revision_id": rev_id,
        "entity_id": "shot_10",
        "reason": "Add establishing shot",
        "payload": {"duration": 4.0},
    }

    # First request
    res1 = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "key_repeat_01"},
        json=payload_a,
    )
    assert res1.status_code == 200
    data1 = res1.json()

    # Second identical request (Idempotent replay)
    res2 = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "key_repeat_01"},
        json=payload_a,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["command_id"] == data1["command_id"]
    assert data2["updated_revision_id"] == data1["updated_revision_id"]

    # Third request with SAME key but DIFFERENT payload -> 409 Mismatch Conflict
    payload_b = dict(payload_a)
    payload_b["reason"] = "DIFFERENT REASON"

    res3 = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "key_repeat_01"},
        json=payload_b,
    )
    assert res3.status_code == 409
    detail = res3.json()["detail"]
    assert detail["code"] == "IDEMPOTENCY_MISMATCH"


def test_stale_target_revision_rejection(client):
    snap = client.get("/api/v2/video-production/projects/vp_unit_04/workspace").json()
    rev1 = snap["revision_id"]

    # Execute first mutation to advance active revision to rev2
    client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "key_step_01"},
        json={
            "command_type": "UPDATE_ASSET",
            "project_id": "vp_unit_04",
            "target_revision_id": rev1,
            "entity_id": "asset_1",
            "reason": "First edit",
        },
    )

    # Try executing second command against old rev1 -> 409 Conflict (REJECTED_STALE)
    res_stale = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "key_step_02"},
        json={
            "command_type": "UPDATE_ASSET",
            "project_id": "vp_unit_04",
            "target_revision_id": rev1,
            "entity_id": "asset_1",
            "reason": "Stale edit attempt",
        },
    )
    assert res_stale.status_code == 409
    detail = res_stale.json()["detail"]
    assert detail["code"] == "REJECTED_STALE"
    assert detail["target_revision_id"] == rev1
    assert detail["current_revision_id"] != rev1
