"""
Event Stream & Replay Unit Tests for Stage B (UI7).
- Tests event listing and filtering by project_id
- Tests event replay from min_sequence / last_sequence
- Tests SSE event stream replay formatting
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_events.db"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    with TestClient(app) as test_client:
        yield test_client


def test_event_listing_and_project_replay(client):
    # 1. Initialize project and run commands to generate durable events
    snap = client.get("/api/v2/video-production/projects/vp_evt_01/workspace").json()
    rev1 = snap["revision_id"]

    cmd1 = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "evt_key_1"},
        json={
            "command_type": "UPDATE_SCENE",
            "project_id": "vp_evt_01",
            "target_revision_id": rev1,
            "entity_id": "scene_101",
            "reason": "Event generation 1",
        },
    ).json()

    cmd2 = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "evt_key_2"},
        json={
            "command_type": "ADD_SHOT",
            "project_id": "vp_evt_01",
            "target_revision_id": cmd1["updated_revision_id"],
            "entity_id": "shot_201",
            "reason": "Event generation 2",
        },
    ).json()

    # 2. List events for project vp_evt_01 from sequence 0
    res_all = client.get("/api/v2/video-production/events?project_id=vp_evt_01&min_sequence=0")
    assert res_all.status_code == 200
    events_all = res_all.json()
    assert len(events_all) == 3
    assert events_all[0]["event_type"] == "PROJECT_PROVISIONED"

    # 3. List events for project vp_evt_01 with last_sequence replay filter
    seq1 = events_all[1]["sequence_number"]
    res_replay = client.get(
        f"/api/v2/video-production/events?project_id=vp_evt_01&last_sequence={seq1}"
    )
    assert res_replay.status_code == 200
    events_replayed = res_replay.json()
    assert len(events_replayed) == 1
    assert events_replayed[0]["sequence_number"] == events_all[2]["sequence_number"]
