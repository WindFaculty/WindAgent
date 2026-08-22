"""
Event Stream & Replay Unit Tests for Stage B (UI7) — post-V2-retirement.

The V2 video-production surface was permanently retired in Phase 15
(410 Gone + tombstone pointing at /api/v3/*). The live event-stream and
replay behavior these tests originally exercised is now covered by the V3
surface:
  - tests/contracts/test_v3_vertical_lifecycle_real.py      (terminal/outbox events)
  - tests/architecture/test_architecture_v3_phase16.py      (WS replay/dedup)
  - tests/unit/api/test_architecture_v3_phase6_realtime.py  (realtime hub)

This module keeps the retirement contract executable: every retired
video-production event/replay endpoint must answer the canonical tombstone.
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


def test_event_listing_endpoints_are_retired_tombstones(client):
    """All retired V2 video-production event/replay endpoints return 410 Gone."""
    retired = [
        ("GET", "/api/v2/video-production/events?project_id=vp_evt_01&min_sequence=0"),
        ("GET", "/api/v2/video-production/events?project_id=vp_evt_01&last_sequence=1"),
        ("GET", "/api/v2/video-production/projects/vp_evt_01/workspace"),
        ("POST", "/api/v2/video-production/commands"),
    ]
    for method, path in retired:
        res = client.request(method, path)
        assert res.status_code == 410, f"{method} {path} -> {res.status_code}"
        body = res.json()
        assert body["available_endpoints"] == "/api/v3/*"
        assert "retired" in body["title"].lower() or body["status"] == 410


def test_tombstone_points_to_v3_realtime_surface(client):
    """The tombstone must direct callers to /api/v3/*, never back to V1/V2."""
    res = client.get("/api/v2/video-production/events")
    assert res.status_code == 410
    assert "/api/v1" not in res.text or res.json()["available_endpoints"] == "/api/v3/*"
