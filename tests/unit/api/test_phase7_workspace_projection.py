"""Phase 7: the desktop workspace reads only durable conversation projections.

Architecture V3 update: the retired /api/v2/conversations/* projection
endpoints are behind the Phase 15 tombstone. The canonical surface is
/api/v3/conversations/*, backed by the same durable OrchestratorService
projections.
"""

from __future__ import annotations


def test_v2_conversation_workspace_endpoints_are_retired(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from windagent_api.main import app

    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'phase7.db'}")
    with TestClient(app) as client:
        created = client.post(
            "/api/v2/conversations/phase7-workspace/goals",
            json={
                "objective": "Ship a durable workspace",
                "subtasks": [
                    {"node_id": "research", "objective": "Research the API"},
                    {
                        "node_id": "implement",
                        "objective": "Implement the workspace",
                        "depends_on": ["research"],
                    },
                ],
            },
        )
        assert created.status_code == 410, created.text
        body = created.json()
        assert body["title"] == "API V2 Retired"
        assert body["available_endpoints"] == "/api/v3/*"

        agents_response = client.get("/api/v2/conversations/phase7-workspace/agents")
        graphs_response = client.get("/api/v2/conversations/phase7-workspace/task-graphs")

    assert agents_response.status_code == 410
    assert graphs_response.status_code == 410


def test_plan_revision_endpoint_keeps_the_old_snapshot_retrievable():
    from fastapi.testclient import TestClient

    from windagent_api.dependencies import get_orchestrator_service
    from windagent_api.main import app

    app.dependency_overrides[get_orchestrator_service] = lambda: object()
    try:
        with TestClient(app) as client:
            revision_url = (
                "/api/v2/conversations/phase7-plan-revision/parent-tasks/parent-1/plan-revisions"
            )
            revised = client.post(
                revision_url,
                json={
                    "base_plan_version_id": "plan-1",
                    "subtasks": [{"node_id": "replacement", "objective": "Replacement task"}],
                },
            )
            history = client.get(
                "/api/v2/conversations/phase7-plan-revision/parent-tasks/parent-1/plan-versions"
            )
    finally:
        app.dependency_overrides.pop(get_orchestrator_service, None)

    assert revised.status_code == 410, revised.text
    assert history.status_code == 410, history.text
