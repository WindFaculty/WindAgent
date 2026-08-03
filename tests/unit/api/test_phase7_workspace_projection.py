"""Phase 7: the desktop workspace reads only durable conversation projections."""

from __future__ import annotations


def test_conversation_workspace_endpoints_expose_agents_and_compact_task_graph(tmp_path, monkeypatch):
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
        assert created.status_code == 201, created.text

        agents_response = client.get("/api/v2/conversations/phase7-workspace/agents")
        graphs_response = client.get("/api/v2/conversations/phase7-workspace/task-graphs")

    assert agents_response.status_code == 200, agents_response.text
    agents = agents_response.json()
    assert {agent["agent_type"] for agent in agents} == {"orchestrator", "research", "coding"}
    coding = next(agent for agent in agents if agent["agent_type"] == "coding")
    for field in (
        "agent_instance_id", "agent_session_id", "canonical_model_id",
        "permission_profile", "worktree_path", "route_lock_id", "provider_binding_id",
    ):
        assert field in coding

    assert graphs_response.status_code == 200, graphs_response.text
    graphs = graphs_response.json()
    assert len(graphs) == 1
    graph = graphs[0]
    assert graph["objective"] == "Ship a durable workspace"
    assert [node["objective"] for node in graph["nodes"]] == [
        "Research the API", "Implement the workspace"
    ]
    assert graph["edges"][0]["from_node_id"] == graph["nodes"][0]["node_id"]
    assert graph["edges"][0]["to_node_id"] == graph["nodes"][1]["node_id"]


def test_plan_revision_endpoint_keeps_the_old_snapshot_retrievable():
    from fastapi.testclient import TestClient

    from windagent_api.dependencies import get_orchestrator_service
    from windagent_api.main import app
    from windagent_orchestration.orchestrator_service import PlanRevisionConflict, PlanRevisionResult

    class RevisionStub:
        async def revise_plan(self, **kwargs):
            if kwargs["base_plan_version_id"] != "plan-1":
                raise PlanRevisionConflict("active plan version changed; reload before revising")
            return PlanRevisionResult(
                conversation_id=kwargs["conversation_id"],
                parent_task_id=kwargs["parent_task_id"],
                base_plan_version_id="plan-1",
                plan_version_id="plan-2",
                version=2,
            )

        async def list_plan_versions(self, **kwargs):
            return [
                {
                    "plan_version_id": "plan-1", "version": 1,
                    "parent_task_id": kwargs["parent_task_id"], "objective": "Original goal",
                    "dag": {"nodes": [{"objective": "Original task"}], "edges": []},
                    "is_active": False, "created_at": None,
                },
                {
                    "plan_version_id": "plan-2", "version": 2,
                    "parent_task_id": kwargs["parent_task_id"], "objective": "Original goal",
                    "dag": {"nodes": [{"objective": "Replacement task"}], "edges": []},
                    "is_active": True, "created_at": None,
                },
            ]

    app.dependency_overrides[get_orchestrator_service] = lambda: RevisionStub()
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
            stale = client.post(
                revision_url,
                json={
                    "base_plan_version_id": "plan-0",
                    "subtasks": [{"node_id": "stale", "objective": "Stale revision"}],
                },
            )
            history = client.get(
                "/api/v2/conversations/phase7-plan-revision/parent-tasks/parent-1/plan-versions"
            )
    finally:
        app.dependency_overrides.pop(get_orchestrator_service, None)

    assert revised.status_code == 201, revised.text
    assert revised.json()["plan_version_id"] == "plan-2"
    assert stale.status_code == 409, stale.text
    assert history.status_code == 200, history.text
    snapshots = history.json()
    assert [snapshot["version"] for snapshot in snapshots] == [1, 2]
    assert [node["objective"] for node in snapshots[0]["dag"]["nodes"]] == ["Original task"]
    assert [node["objective"] for node in snapshots[1]["dag"]["nodes"]] == ["Replacement task"]
    assert snapshots[0]["is_active"] is False
    assert snapshots[1]["is_active"] is True
