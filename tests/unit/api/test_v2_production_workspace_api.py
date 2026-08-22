"""
Stage B Production Workspace & Event Replay — retirement contract tests.

The V2 video-production workspace (snapshot / canonical commands / event
replay HTTP surface) was retired with API V2 (Phase 15). The canonical
production surface is /api/v3/* (see routers/v3/production.py) and the
canonical realtime replay is the /ws hub with per-aggregate sequence
cursors. These tests pin the CURRENT default contract: every retired
route answers 410 Gone pointing at /api/v3/*.
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


def test_workspace_snapshot_route_is_retired(client):
    res = client.get("/api/v2/video-production/projects/vp_unit_01/workspace")
    assert res.status_code == 410, res.text
    body = res.json()
    assert body["title"] == "API V2 Retired"
    assert body["available_endpoints"] == "/api/v3/*"


def test_canonical_command_route_is_retired(client):
    res = client.post(
        "/api/v2/video-production/commands",
        headers={"X-Idempotency-Key": "idemp_cmd_001"},
        json={
            "command_type": "UPDATE_SCENE",
            "project_id": "vp_unit_02",
            "target_revision_id": "rev_1",
            "entity_id": "scene_01",
            "reason": "Dialogue refinement",
            "payload": {"text": "Updated scene text"},
        },
    )
    assert res.status_code == 410, res.text
    assert res.json()["title"] == "API V2 Retired"


def test_production_events_replay_route_is_retired(client):
    res = client.get("/api/v2/video-production/events?project_id=vp_evt_01&min_sequence=0")
    assert res.status_code == 410, res.text
    assert res.json()["detail"].startswith("API V2 has been permanently retired")


def test_v3_production_surface_is_available(client):
    """The canonical V3 production router answers on its plan surface.

    P1.0 truth repair: GET is read-only, so a fresh episode id yields
    404 PRODUCTION_PLAN_NOT_CREATED — proving the route is live
    (not the 410 tombstone) and no longer fabricates a plan on read.
    """
    res = client.get("/api/v3/episodes/ep_none/production")
    assert res.status_code == 404, res.text
    body = res.json()
    assert body["detail"]["error_code"] == "PRODUCTION_PLAN_NOT_CREATED"
    assert body["detail"]["message"].startswith("No production plan initialized")
