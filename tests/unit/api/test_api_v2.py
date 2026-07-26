"""
Unit and contract tests for WindAgent API V2. V1 compatibility has been removed (Phase 8).
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
    assert task_data["status"] in ("CREATED", "RECEIVED", "PENDING", "pending")
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


def test_api_v1_tombstone_returns_410():
    """Test that all V1 endpoints return 410 Gone after removal."""
    # Test GET /api/v1/tasks
    r_v1_get = client.get("/api/v1/tasks")
    assert r_v1_get.status_code == 410
    assert r_v1_get.json()["title"] == "API V1 Removed"
    assert r_v1_get.json()["detail"] == "API V1 has been permanently removed. Please migrate to API V2."

    # Test POST /api/v1/tasks
    r_v1_post = client.post("/api/v1/tasks", json={"prompt": "test"})
    assert r_v1_post.status_code == 410
    assert r_v1_post.json()["status"] == 410

    # Test parity matrix endpoint is removed
    r_parity = client.get("/api/v2/parity-matrix")
    assert r_parity.status_code == 404
