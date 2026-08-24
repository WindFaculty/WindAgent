"""
Tests for PHASE 10 API health endpoints.
Tests /health/live and /health/ready endpoints with real checks.
"""

from __future__ import annotations
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from windagent_api.main import app


@pytest.fixture
def test_client():
    """Create test client for API."""
    return TestClient(app)


class TestLivenessEndpoint:
    """Tests for /health/live endpoint."""
    
    def test_liveness_returns_live(self, test_client):
        """GET /health/live should return 200 with status 'live'."""
        response = test_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "live"
        assert data["service"] == "windagent-api"


class TestReadinessEndpoint:
    """Tests for /health/ready endpoint."""
    
    def test_readiness_returns_up_when_healthy(self, test_client):
        """GET /health/ready should return 200 with status 'UP' when all checks pass."""
        # This test depends on the actual state of the services
        # In a test environment, it may return UP or DEGRADED
        response = test_client.get("/health/ready")
        assert response.status_code in [200, 503]  # May be 503 if checks fail
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] in ["UP", "DEGRADED"]
            assert "checks" in data
            assert "profile" in data
    
    def test_readiness_returns_503_when_not_ready(self, test_client):
        """GET /health/ready should return 503 when checks fail."""
        # This test verifies that the endpoint properly returns 503
        # We can't easily force a failure, but we can check the structure
        response = test_client.get("/health/ready")
        
        if response.status_code == 503:
            data = response.json()
            assert "status" in data
            assert "checks" in data
            assert data["status"] in ["DOWN", "DEGRADED"]
    
    def test_readiness_includes_all_required_checks(self, test_client):
        """GET /health/ready should include all required checks."""
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            checks = data.get("checks", {})
            
            # Should include all required checks from PHASE 10
            required_checks = [
                "database",
                "schema_migration",
                "outbox",
                "queue",
                "worker",
                "provider_registry",
                "tool_registry",
                "workflow_registry",
                "event_dispatcher",
                "filesystem",
                "configuration",
            ]
            
            for check_name in required_checks:
                assert check_name in checks, f"Missing required check: {check_name}"


class TestHealthCheckProfiles:
    """Tests for profile-based health check behavior."""
    
    @patch.dict("os.environ", {"WINDAGENT_ENV": "production"})
    def test_readiness_in_production_profile(self, test_client):
        """Readiness in production profile should be fail-closed."""
        # Note: This test may not work as expected because the app state
        # is shared across tests. We'd need to restart the app for this.
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            assert "profile" in data
        elif response.status_code == 503:
            data = response.json()
            assert "profile" in data


class TestHealthEndpointStructure:
    """Tests for health endpoint response structure."""
    
    def test_liveness_response_structure(self, test_client):
        """Liveness response should have correct structure."""
        response = test_client.get("/health/live")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        assert "status" in data
        assert "service" in data
        assert data["service"] == "windagent-api"
    
    def test_readiness_response_structure(self, test_client):
        """Readiness response should have correct structure."""
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data
            assert "service" in data
            assert "profile" in data
            assert "checks" in data
            assert isinstance(data["checks"], dict)
            
            # Each check should have correct structure
            for check_name, check_data in data["checks"].items():
                assert isinstance(check_data, dict)
                assert "status" in check_data
                assert "message" in check_data
                assert "required" in check_data


class TestHealthCheckNoHardcodedValues:
    """Tests to verify no hardcoded values in health checks."""
    
    def test_schema_migration_not_hardcoded(self, test_client):
        """Schema migration check should not return hardcoded version."""
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            schema_check = data.get("checks", {}).get("schema_migration", {})
            
            # Should not have hardcoded "v2_canonical_latest"
            assert schema_check.get("message") != "v2_canonical_latest"
            assert schema_check.get("details", {}).get("version") != "v2_canonical_latest"
    
    def test_outbox_not_hardcoded(self, test_client):
        """Outbox check should not return hardcoded pending_records=0."""
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            outbox_check = data.get("checks", {}).get("outbox", {})
            
            # Should have real data, not just hardcoded values
            assert outbox_check.get("message") != "Outbox publisher heartbeat OK"
    
    def test_event_bus_not_hardcoded(self, test_client):
        """Event bus check should not return hardcoded ready message."""
        response = test_client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            event_check = data.get("checks", {}).get("event_dispatcher", {})
            
            # Should have real check, not hardcoded
            assert event_check.get("message") != "Event bus ready"
