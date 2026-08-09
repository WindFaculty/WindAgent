"""
Integration Test Gate: VP3D_UI_P7_REALTIME_STATE_VERIFIED.

Verifies end-to-end convergence between durable backend query snapshot,
canonical mutating commands, event logging, and real-time event replay.
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_vp3d_gate.db"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    with TestClient(app) as test_client:
        yield test_client


def test_vp3d_ui_p7_realtime_state_verified(client):
    project_id = "vp_gate_project"

    # Step 1: Query initial workspace snapshot
    snap_res = client.get(f"/api/v2/video-production/projects/{project_id}/workspace")
    assert snap_res.status_code == 200, snap_res.text
    snapshot = snap_res.json()

    assert snapshot["project_id"] == project_id
    init_rev = snapshot["revision_id"]
    init_seq = snapshot["current_sequence"]
    assert init_seq >= 1

    # Step 2: Dispatch canonical mutating command
    cmd_res = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "gate_key_001"},
        json={
            "command_type": "UPDATE_SCENE",
            "project_id": project_id,
            "target_revision_id": init_rev,
            "entity_id": "scene_hero",
            "reason": "Verify realtime state sync",
            "payload": {"title": "Hero Scene Refined"},
        },
    )
    assert cmd_res.status_code == 200, cmd_res.text
    cmd_out = cmd_res.json()
    assert cmd_out["status"] == "COMPLETED"
    updated_rev = cmd_out["updated_revision_id"]
    updated_seq = cmd_out["current_sequence"]
    assert updated_seq == init_seq + 1

    # Step 3: Replay domain events from initial sequence
    events_res = client.get(
        f"/api/v2/video-production/events?project_id={project_id}&last_sequence={init_seq}"
    )
    assert events_res.status_code == 200, events_res.text
    replayed_events = events_res.json()
    assert len(replayed_events) == 1
    event = replayed_events[0]
    assert event["sequence_number"] == updated_seq
    assert event["event_type"] == "WORKSPACE_COMMAND_UPDATE_SCENE"

    # Step 4: Verify snapshot query reflects new active revision and sequence
    latest_snap_res = client.get(f"/api/v2/video-production/projects/{project_id}/workspace")
    assert latest_snap_res.status_code == 200
    latest_snap = latest_snap_res.json()

    assert latest_snap["revision_id"] == updated_rev
    assert latest_snap["current_sequence"] == updated_seq

    # Gate assertion: Real-time state verified across snapshot, command execution, and replay
    print("GATE VERIFIED: VP3D_UI_P7_REALTIME_STATE_VERIFIED passed.")
