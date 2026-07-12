"""Contract tests for API versioning and compatibility routes.

Ensures that all routing rules defined in main.py are correctly resolved.
"""
from __future__ import annotations

import pytest


def test_compatibility_health_ok(client):
    """GET /health compatibility route is exposed at root."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "windagent-backend"


def test_compatibility_models_health_ok(client):
    """GET /models/health compatibility route is exposed at root."""
    resp = client.get("/models/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["online"] is True


def test_versioned_health_ok(client):
    """GET /api/v1/health is versioned and exposed."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_versioned_models_health_ok(client):
    """GET /api/v1/models/health is versioned and exposed."""
    resp = client.get("/api/v1/models/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["online"] is True


def test_unversioned_business_routes_return_404(client):
    """Business routes MUST NOT be exposed at root level (unversioned)."""
    # Unversioned sessions
    resp = client.post("/sessions")
    assert resp.status_code == 404

    # Unversioned permissions config
    resp = client.get("/permissions/config")
    assert resp.status_code == 404

    # Unversioned tools list
    resp = client.get("/tools")
    assert resp.status_code == 404

    # Unversioned models list
    resp = client.get("/models")
    assert resp.status_code == 404


def test_versioned_business_routes_resolve_correctly(client):
    """Business routes are correctly resolved under /api/v1 prefix."""
    # Versioned sessions
    resp_sess = client.post("/api/v1/sessions")
    assert resp_sess.status_code == 201
    assert resp_sess.json()["session_id"]

    # Versioned permissions config
    resp_perm = client.get("/api/v1/permissions/config")
    assert resp_perm.status_code == 200

    # Versioned tools list
    resp_tools = client.get("/api/v1/tools")
    assert resp_tools.status_code == 200

    # Versioned models list
    resp_models = client.get("/api/v1/models")
    assert resp_models.status_code == 200

    # Versioned agents list
    resp_agents = client.get("/api/v1/agents")
    assert resp_agents.status_code == 200
