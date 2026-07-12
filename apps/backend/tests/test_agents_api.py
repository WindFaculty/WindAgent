"""Unit tests for the new Agents Registry API endpoints."""
from __future__ import annotations

import pytest


def test_list_agents(client):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) > 0
    # Coder should be seeded by default
    coder = next((a for a in agents if a["id"] == "coder"), None)
    assert coder is not None
    assert coder["name"] == "Coder"
    assert coder["runtime_type"] == "hermes"


def test_get_agent(client):
    resp = client.get("/api/v1/agents/coder")
    assert resp.status_code == 200
    coder = resp.json()
    assert coder["id"] == "coder"
    assert coder["name"] == "Coder"


def test_get_agent_unknown(client):
    resp = client.get("/api/v1/agents/non-existent-agent-id-123")
    assert resp.status_code == 404


def test_agent_summary(client):
    resp = client.get("/api/v1/agents/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert "total" in summary
    assert "running" in summary
    assert "idle" in summary
    assert "offline" in summary


def test_agent_control_endpoints(client):
    # Start agent
    resp = client.post("/api/v1/agents/coder/start")
    assert resp.status_code == 200
    assert resp.json()["state"] == "Idle"

    # Stop agent
    resp = client.post("/api/v1/agents/coder/stop")
    assert resp.status_code == 200
    assert resp.json()["state"] == "Offline"

    # Restart agent
    resp = client.post("/api/v1/agents/coder/restart")
    assert resp.status_code == 200
    assert resp.json()["state"] == "Idle"


def test_agent_sessions_list(client):
    resp = client.get("/api/v1/agents/coder/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_agent_activity_list(client):
    resp = client.get("/api/v1/agents/coder/activity")
    assert resp.status_code == 200
    assert len(resp.json()) > 0
