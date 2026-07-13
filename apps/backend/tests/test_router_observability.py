"""Phase 6 — Tests for router runtime observability endpoints."""
from __future__ import annotations

import pytest


class TestRuntimeSummary:
    """Tests for GET /router/runtime/summary."""

    def test_summary_returns_200_with_empty_db(self, client):
        """Empty DB must return a valid response, not a 500 or crash."""
        res = client.get("/router/runtime/summary")
        assert res.status_code == 200

        data = res.json()
        # Must contain required keys
        assert "request_count_by_agent" in data
        assert "request_count_by_model" in data
        assert "avg_latency_ms" in data
        assert "error_rate" in data
        assert "fallback_count" in data
        assert "quota_usage" in data
        assert "last_executions" in data
        assert "degraded_providers" in data
        assert "total_requests_24h" in data

    def test_summary_does_not_expose_secrets(self, client):
        """Response must not contain known secret header keys."""
        res = client.get("/router/runtime/summary")
        assert res.status_code == 200

        raw_text = res.text.lower()
        # These strings must never appear in the response
        assert "api_key" not in raw_text
        assert "bearer" not in raw_text
        assert "sk-" not in raw_text

    def test_summary_empty_db_has_zero_counts(self, client):
        """With empty DB, all counters must be 0."""
        res = client.get("/router/runtime/summary")
        assert res.status_code == 200

        data = res.json()
        assert data["total_requests_24h"] == 0
        assert data["avg_latency_ms"] == 0.0
        assert data["error_rate"] == 0.0
        assert data["fallback_count"] == 0


class TestRuntimeExecutions:
    """Tests for GET /router/runtime/executions."""

    def test_executions_returns_200_with_empty_db(self, client):
        """Empty DB must return empty list, not crash."""
        res = client.get("/router/runtime/executions")
        assert res.status_code == 200

        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_executions_limit_param_respected(self, client):
        """?limit= parameter must be accepted."""
        res = client.get("/router/runtime/executions?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert len(data) <= 10

    def test_executions_rejects_invalid_limit(self, client):
        """?limit=0 or negative should be rejected (ge=1 validation)."""
        res = client.get("/router/runtime/executions?limit=0")
        assert res.status_code == 422  # Pydantic validation error


class TestProvidersHealth:
    """Tests for GET /router/runtime/providers/health."""

    def test_providers_health_returns_200(self, client):
        """Endpoint must return 200 even with no runtime data."""
        res = client.get("/router/runtime/providers/health")
        assert res.status_code == 200

        data = res.json()
        assert isinstance(data, list)
