"""
Test suite for PHASE 8 — Loai bo API V1 ngay (API V1 Removal)

This test suite verifies that:
1. API V1 routes have been completely removed
2. Tombstone handler returns 410 Gone for all /api/v1/* requests
3. API V2 endpoints are still operational
4. No V1 compatibility code remains in the API
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app

client = TestClient(app)


class TestApiV1Removal:
    """Test suite verifying API V1 has been completely removed."""

    def test_v1_tasks_endpoint_returns_410(self):
        """GET /api/v1/tasks should return 410 Gone."""
        response = client.get("/api/v1/tasks")
        assert response.status_code == 410
        data = response.json()
        assert data["title"] == "API V1 Removed"
        assert data["status"] == 410
        assert data["detail"] == "API V1 has been permanently removed. Please migrate to API V2."
        assert "removal_date" in data
        assert "migration_guide" in data
        assert "available_endpoints" in data

    def test_v1_tasks_post_returns_410(self):
        """POST /api/v1/tasks should return 410 Gone."""
        response = client.post("/api/v1/tasks", json={"prompt": "test"})
        assert response.status_code == 410
        assert response.json()["title"] == "API V1 Removed"

    def test_v1_runs_endpoint_returns_410(self):
        """GET /api/v1/runs should return 410 Gone."""
        response = client.get("/api/v1/runs")
        assert response.status_code == 410
        assert response.json()["status"] == 410

    def test_v1_models_endpoint_returns_410(self):
        """GET /api/v1/models should return 410 Gone."""
        response = client.get("/api/v1/models")
        assert response.status_code == 410
        assert response.json()["title"] == "API V1 Removed"

    def test_v1_sessions_endpoint_returns_410(self):
        """POST /api/v1/sessions should return 410 Gone."""
        response = client.post("/api/v1/sessions")
        assert response.status_code == 410
        assert response.json()["status"] == 410

    def test_v1_agents_endpoint_returns_410(self):
        """GET /api/v1/agents should return 410 Gone."""
        response = client.get("/api/v1/agents")
        assert response.status_code == 410
        assert response.json()["title"] == "API V1 Removed"

    def test_v1_parity_matrix_removed(self):
        """GET /api/v2/parity-matrix should return 404 (route removed)."""
        response = client.get("/api/v2/parity-matrix")
        assert response.status_code == 404

    def test_v1_all_http_methods_return_410(self):
        """All HTTP methods on /api/v1/* should return 410."""
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
        for method in methods:
            response = client.request(method, "/api/v1/anything")
            assert response.status_code == 410, f"Method {method} should return 410"


class TestApiV2StillOperational:
    """Verify API V2 endpoints are still working after V1 removal."""

    def test_v2_tasks_still_works(self):
        """POST /api/v2/tasks should still work."""
        response = client.post("/api/v2/tasks", json={
            "prompt": "Test task",
            "workflow_name": "test"
        })
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data

    def test_v2_sessions_still_works(self):
        """POST /api/v2/sessions should still work."""
        response = client.post("/api/v2/sessions", json={
            "session_name": "Test Session"
        })
        assert response.status_code in [200, 201]

    def test_v2_providers_still_works(self):
        """GET /api/v2/providers should still work."""
        response = client.get("/api/v2/providers")
        assert response.status_code == 200

    def test_v2_health_still_works(self):
        """Health endpoints should still work."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "live"


class TestNoV1ImportsInApi:
    """Verify no V1 imports remain in the API code."""

    def test_compatibility_module_removed(self):
        """The compatibility module should not exist."""
        import os
        compat_path = "D:/code_ca_nhan/WindAgent/apps/api/windagent_api/routers/compatibility.py"
        assert not os.path.exists(compat_path), "V1 compatibility module should be removed"

    def test_no_v1_imports_in_main(self):
        """main.py should not import v1_router or parity_router."""
        import inspect
        from windagent_api import main
        source = inspect.getsource(main)
        assert "v1_router" not in source, "v1_router should not be imported"
        assert "parity_router" not in source, "parity_router should not be imported"

    def test_no_v1_router_registration(self):
        """main.py should not register v1_router or parity_router."""
        import inspect
        from windagent_api import main
        source = inspect.getsource(main)
        assert "app.include_router(v1_router)" not in source
        assert "app.include_router(parity_router)" not in source
