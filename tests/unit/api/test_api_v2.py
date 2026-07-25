"""
Unit and contract tests for WindAgent API V2 and V1 compatibility adapter (Phase 12).
"""

from fastapi.testclient import TestClient
from windagent_api.main import app

client = TestClient(app)


def test_health_and_architecture_endpoints():
    r1 = client.get("/health/live")
    assert r1.status_code == 200
    assert r1.json()["status"] == "live"

    r2 = client.get("/internal/architecture")
    assert r2.status_code == 200
    assert r2.json()["architecture"] == "V2"
    assert r2.json()["status"] in ("scaffold", "canonical_api_v2_production")


def test_api_v2_tasks_crud_and_cancellation():
    # Create task
    r_create = client.post("/api/v2/tasks", json={"prompt": "Fix bug in calculation module", "workflow_name": "bugfix"})
    assert r_create.status_code == 201
    task_data = r_create.json()
    task_id = task_data["task_id"]
    assert task_data["status"] in ("CREATED", "RECEIVED")
    assert task_data["workflow_name"] == "bugfix"

    # List tasks
    r_list = client.get("/api/v2/tasks")
    assert r_list.status_code == 200
    assert len(r_list.json()) >= 1

    # Get task
    r_get = client.get(f"/api/v2/tasks/{task_id}")
    assert r_get.status_code == 200
    assert r_get.json()["task_id"] == task_id

    # Cancel task
    r_cancel = client.post(f"/api/v2/tasks/{task_id}/cancel")
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "CANCELLED"


def test_api_v2_all_resources_endpoints():
    # Runs
    r_runs = client.get("/api/v2/runs")
    assert r_runs.status_code == 200

    # Workflows
    r_wf = client.get("/api/v2/workflows")
    assert r_wf.status_code == 200
    assert len(r_wf.json()) == 8  # 8 workflow packs

    # Events
    r_evt = client.get("/api/v2/events")
    assert r_evt.status_code == 200

    # Providers
    r_prov = client.get("/api/v2/providers")
    assert r_prov.status_code == 200

    # Tools
    r_tools = client.get("/api/v2/tools")
    assert r_tools.status_code == 200

    # Permissions
    r_perm = client.post("/api/v2/permissions/evaluate", json={"action": "read_file", "target": "main.py"})
    assert r_perm.status_code == 200
    assert r_perm.json()["allowed"] is True

    # Artifacts
    r_art = client.get("/api/v2/artifacts")
    assert r_art.status_code == 200

    # Evals
    r_eval = client.get("/api/v2/evals/reports")
    assert r_eval.status_code == 200
    assert r_eval.json()["passed"] is True


def test_v1_compatibility_and_parity_matrix():
    # V1 tasks delegate to V2
    r_v1_create = client.post("/api/v1/tasks", json={"prompt": "V1 Task test", "workflow_name": "feature"})
    assert r_v1_create.status_code == 201
    assert r_v1_create.json()["workflow_name"] == "feature"

    # Parity matrix check
    r_parity = client.get("/api/v2/parity-matrix")
    assert r_parity.status_code == 200
    matrix = r_parity.json()
    assert len(matrix) >= 5
    assert all(entry["status"] == "PARITY_OK" for entry in matrix)
