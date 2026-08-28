"""
Phase 15 — API V2 Retirement Test Suite.

Verifies:
1. All /api/v2/* endpoints return 410 Gone tombstone in default production configuration.
2. OpenAPI schema contains zero /api/v2/ endpoints.
3. Canonical V3 endpoints and health endpoints operate normally.
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client(monkeypatch):
    # Full-suite ordering runs stub-container tests first (they assign
    # SimpleNamespace containers onto app.state and never restore), so this
    # file forces get_container to compose the real one; monkeypatch puts
    # whatever was there back afterwards.
    monkeypatch.setattr(app.state, "container", None, raising=False)
    return TestClient(app)


def test_v2_endpoints_return_410_tombstone(client):
    """Calling retired /api/v2 endpoints must return 410 Gone."""
    retired_paths = [
        ("GET", "/api/v2/providers"),
        ("POST", "/api/v2/tasks"),
        ("GET", "/api/v2/sessions"),
        ("GET", "/api/v2/browser/sessions"),
        ("GET", "/api/v2/video-production/projects/p1/workspace"),
        ("GET", "/api/v2/screenplay/projects/p1/screenplay"),
        ("GET", "/api/v2/memory"),
        ("GET", "/api/v2/workflows"),
        ("GET", "/api/v2/events"),
        ("GET", "/api/v2/skills"),
        ("GET", "/api/v2/tools"),
        ("GET", "/api/v2/plugins"),
        ("GET", "/api/v2/evals"),
        ("GET", "/api/v2/observability/metrics"),
    ]

    for method, path in retired_paths:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json={})
        assert res.status_code == 410, f"Expected 410 for {method} {path}, got {res.status_code}"
        data = res.json()
        assert data.get("status") == 410
        assert "API V2 has been permanently retired" in data.get("detail", "")


def test_openapi_schema_contains_zero_v2_paths(client):
    """OpenAPI specification must not expose any /api/v2/ endpoints."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema.get("paths", {})

    v2_paths = [p for p in paths.keys() if p.startswith("/api/v2")]
    assert len(v2_paths) == 0, f"Expected 0 /api/v2 paths in OpenAPI, found {len(v2_paths)}: {v2_paths}"


def test_internal_architecture_reports_v3(client):
    """Internal architecture endpoint reports V3 production status."""
    res = client.get("/internal/architecture")
    assert res.status_code == 200
    data = res.json()
    assert data["architecture"] == "V3"
    assert data["status"] == "canonical_api_v3_production"
    assert data["api_version"] == "v3"


def test_v3_endpoints_are_active(client):
    """Canonical V3 endpoints remain active and functional."""
    health_res = client.get("/health/live")
    assert health_res.status_code == 200

    v3_health = client.get("/api/v3/system/health")
    assert v3_health.status_code == 200

    dashboard_res = client.get("/api/v3/dashboard/summary")
    assert dashboard_res.status_code == 200
