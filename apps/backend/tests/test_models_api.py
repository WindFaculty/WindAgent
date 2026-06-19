"""Tests for the /models/health endpoint (Phase 4).

The conftest forces WINDAGENT_MODEL_BACKEND=mock so we can assert the
endpoint shape against the MockModelClient without a real Ollama.
"""
from __future__ import annotations

import pytest


def test_models_health_returns_200_with_expected_shape(client):
    r = client.get("/models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    assert body["online"] is True
    assert body["model"].startswith("mock:")
    assert body["latency_ms"] is not None
    assert body["error"] is None


def test_models_health_unknown_path_returns_404(client):
    r = client.get("/models/health/extra")
    assert r.status_code == 404


def test_models_health_reflects_offline_state(app_state):
    """If the underlying model client reports offline, the endpoint
    reflects that. Swap the planner on the live app.state so the same
    TestClient context is reused."""
    from services.model_client import MockModelClient
    from services.planner_service import PlannerService

    # Swap in a failing client.
    failing = MockModelClient(fail_with_offline=True)
    app_state.model_client = failing
    app_state.planner_service = PlannerService(client=failing)

    from fastapi.testclient import TestClient
    from main import app

    # Reuse the live TestClient via ASGI transport (no lifespan restart).
    c = TestClient(app)
    r = c.get("/models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["online"] is False
    assert body["error"] == "mock offline"


def test_get_models_health_includes_model_name(client):
    r = client.get("/models/health")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["model"], str)
    assert len(body["model"]) > 0