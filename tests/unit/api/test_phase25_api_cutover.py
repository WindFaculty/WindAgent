"""
Phase 25 Unit and E2E Integration Tests: Canonical API Cutover.

Historical context: Phase 25 cut over to the canonical API V2 surface.
Architecture V3 supersedes it (Phase 15): /api/v2/* is retired behind a
410 Gone tombstone by default (ENABLE_V2_API=false) and /api/v3/* is the
canonical surface. These tests verify the CURRENT default contract:
health probes fail closed, V1/V2 tombstones answer 410, and RFC 7807
error envelopes are stable.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "tools", "apps/api"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_liveness_and_readiness_probes(client):
    """Readiness fails closed when required runtime dependencies are absent."""
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "live"

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 503
    assert res_ready.json()["status"] == "DOWN"
    assert res_ready.json()["checks"]["worker"]["status"] != "UP"
    assert "checks" in res_ready.json()


def test_api_v2_tombstone_default_contract(client):
    """With default settings every /api/v2/* route returns the 410 tombstone."""
    endpoints = [
        ("get", "/api/v2/sessions"),
        ("post", "/api/v2/tasks"),
        ("get", "/api/v2/runs"),
        ("get", "/api/v2/workflows"),
        ("get", "/api/v2/events"),
        ("get", "/api/v2/providers"),
        ("get", "/api/v2/tools"),
        ("get", "/api/v2/permissions"),
        ("get", "/api/v2/artifacts"),
        ("get", "/api/v2/memory"),
        ("get", "/api/v2/plugins"),
        ("get", "/api/v2/skills"),
        ("get", "/api/v2/evals"),
        ("get", "/api/v2/observability/spans"),
    ]

    for method, ep in endpoints:
        res = getattr(client, method)(ep)
        assert res.status_code == 410, f"Endpoint {ep} failed with status {res.status_code}"
        body = res.json()
        assert body["title"] == "API V2 Retired"
        assert body["available_endpoints"] == "/api/v3/*"


def test_rfc7807_error_response_mapping(client):
    """Verify structured error responses on the canonical surface.

    V3 routers raise FastAPI HTTPException -> {"detail": ...}; domain errors
    map to the RFC 7807 problem envelope in main.py.
    """
    res = client.get("/api/v3/projects/non_existent_project_id_xyz")
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data or "title" in data


def test_api_v3_canonical_surface_accessible(client):
    """The canonical V3 system surface answers with health metadata."""
    res = client.get("/api/v3/system/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
