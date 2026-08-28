"""
Phase 6 Contract Test Suite — Dashboard & Monitoring V3 Endpoints.
Verifies canonical system metrics, health, dashboard summary aggregation, monitoring telemetry,
and realtime WebSocket streaming contracts.
"""

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPhase6DashboardAndMonitoringContracts:
    def test_system_metrics_endpoint_contract(self, client: TestClient):
        """Verify GET /api/v3/system/metrics returns canonical SystemMetrics schema."""
        response = client.get("/api/v3/system/metrics")
        assert response.status_code == 200
        data = response.json()

        assert "sampled_at" in data
        assert "cpu" in data
        assert "memory" in data
        assert "gpu" in data
        assert "gpu_supported" in data
        assert "disk" in data
        assert "process" in data

        # CPU fields
        cpu = data["cpu"]
        assert "usage_percent" in cpu
        assert "cores_count" in cpu
        assert isinstance(cpu["cores_count"], int)
        assert cpu["cores_count"] >= 1

        # Memory fields
        mem = data["memory"]
        assert "total_bytes" in mem
        assert "used_bytes" in mem
        assert "usage_percent" in mem
        assert mem["total_bytes"] > 0

        # Disk fields
        disk = data["disk"]
        assert "total_bytes" in disk
        assert "used_bytes" in disk

        # Process fields
        proc = data["process"]
        assert "pid" in proc
        assert "cpu_percent" in proc
        assert "memory_bytes" in proc
        assert "threads_count" in proc
        assert "uptime_seconds" in proc

        # GPU metrics: boolean supported check (no fake values)
        assert isinstance(data["gpu_supported"], bool)
        assert isinstance(data["gpu"], list)

    def test_system_health_endpoint_contract(self, client: TestClient):
        """Verify GET /api/v3/system/health returns canonical health checks."""
        response = client.get("/api/v3/system/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in data
        assert "version" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_dashboard_summary_endpoint_contract(self, client: TestClient):
        """Verify GET /api/v3/dashboard/summary aggregates all required studio domains."""
        response = client.get("/api/v3/dashboard/summary")
        assert response.status_code == 200
        data = response.json()

        assert "sampled_at" in data
        assert "projects" in data
        assert "episodes" in data
        assert "runs" in data
        assert "agents" in data
        assert "providers" in data
        assert "activity_by_timeframe" in data
        assert "model_usage" in data
        assert "storage" in data
        assert "recent_activities" in data

        # Projects summary
        assert data["projects"]["total"] >= 0
        assert data["projects"]["active"] >= 0

        # Episodes summary
        assert data["episodes"]["total"] >= 0
        assert data["episodes"]["active"] >= 0

        # Runs summary
        assert data["runs"]["total"] >= 0
        assert data["runs"]["running"] >= 0

        # Agents summary
        assert data["agents"]["total"] >= 0
        assert isinstance(data["agents"]["active_roles"], list)

        # Providers summary
        assert data["providers"]["total"] >= 0
        assert data["providers"]["healthy"] >= 0

        # Activity timeframes
        timeframes = data["activity_by_timeframe"]
        for tf in ["24h", "7d", "30d", "90d"]:
            assert tf in timeframes
            assert isinstance(timeframes[tf], list)
            if len(timeframes[tf]) > 0:
                point = timeframes[tf][0]
                assert "label" in point
                assert "total_activity" in point

        # Model usage
        assert isinstance(data["model_usage"], list)
        if len(data["model_usage"]) > 0:
            m = data["model_usage"][0]
            assert "model_id" in m
            assert "name" in m
            assert "tokens_per_second" in m
            assert "latency_ms" in m

        # Storage — honest zeros when workspace empty (no mock baseline)
        assert data["storage"]["workspace_used_bytes"] >= 0
        assert data["storage"]["workspace_total_bytes"] > 0

    def test_monitoring_workers_contract(self, client: TestClient):
        """Verify GET /api/v3/monitoring/workers returns worker pool telemetry."""
        response = client.get("/api/v3/monitoring/workers")
        assert response.status_code == 200
        data = response.json()

        assert "workers" in data
        assert "total_workers" in data
        assert "active_workers" in data
        assert data["total_workers"] >= len(data["workers"])

    def test_monitoring_providers_contract(self, client: TestClient):
        """Verify GET /api/v3/monitoring/providers returns provider health and latency metrics."""
        response = client.get("/api/v3/monitoring/providers")
        assert response.status_code == 200
        data = response.json()

        assert "providers" in data
        assert len(data["providers"]) > 0
        for p in data["providers"]:
            assert "provider_id" in p
            assert "name" in p
            assert "status" in p
            assert "avg_latency_ms" in p
            assert "error_rate_percent" in p

    def test_monitoring_agents_contract(self, client: TestClient):
        """Verify GET /api/v3/monitoring/agents returns agent execution metrics."""
        response = client.get("/api/v3/monitoring/agents")
        assert response.status_code == 200
        data = response.json()

        assert "agents" in data
        assert len(data["agents"]) > 0
        for a in data["agents"]:
            assert "agent_id" in a
            assert "role" in a
            assert "avg_turn_ms" in a

    def test_monitoring_queues_contract(self, client: TestClient):
        """Verify GET /api/v3/monitoring/queues returns queue depths and throughput."""
        response = client.get("/api/v3/monitoring/queues")
        assert response.status_code == 200
        data = response.json()

        assert "queues" in data
        assert len(data["queues"]) > 0
        for q in data["queues"]:
            assert "queue_name" in q
            assert "depth" in q
            assert "throughput_per_sec" in q

    def test_monitoring_runs_contract(self, client: TestClient):
        """Verify GET /api/v3/monitoring/runs returns recent pipeline execution runs."""
        response = client.get("/api/v3/monitoring/runs")
        assert response.status_code == 200
        data = response.json()

        assert "runs" in data
        assert isinstance(data["runs"], list)

    def test_websocket_system_metrics_stream(self, client: TestClient):
        """Verify WebSocket /ws/v3/system/metrics establishes connection and streams payload."""
        with client.websocket_connect("/ws/v3/system/metrics") as websocket:
            data = websocket.receive_json()
            assert data["event"] == "system.metrics"
            assert "payload" in data
            assert "sampled_at" in data["payload"]
            assert "cpu" in data["payload"]
            assert "memory" in data["payload"]
