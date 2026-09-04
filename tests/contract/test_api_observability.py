"""HTTP propagation, telemetry, and scrape-surface contracts."""

from __future__ import annotations

import httpx
from windagent.platform.configuration.settings import Settings
from windagent.platform.observability import InMemoryTelemetry
from windagent_api.app import create_app


def _settings() -> Settings:
    return Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:")


async def test_http_continues_w3c_trace_and_returns_causal_headers() -> None:
    telemetry = InMemoryTelemetry("api-test")
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    correlation_id = "4b528176-334d-4c7e-bde7-0c44d42c1c1f"
    app = create_app(_settings(), telemetry=telemetry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://v2.test"
    ) as client:
        response = await client.get(
            "/health",
            headers={
                "traceparent": f"00-{trace_id}-00f067aa0ba902b7-01",
                "x-correlation-id": correlation_id,
            },
        )

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == trace_id
    assert response.headers["x-correlation-id"] == correlation_id
    assert response.headers["traceparent"].startswith(f"00-{trace_id}-")
    assert telemetry.spans[-1].name == "http.server.request"
    assert telemetry.spans[-1].attributes["trace_id"] == trace_id
    assert telemetry.events[-1].name == "http.request.completed"


async def test_invalid_trace_is_replaced_and_metrics_are_scrapeable() -> None:
    telemetry = InMemoryTelemetry("api-test")
    app = create_app(_settings(), telemetry=telemetry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://v2.test"
    ) as client:
        health = await client.get("/health", headers={"traceparent": "invalid"})
        metrics = await client.get("/metrics")

    assert len(health.headers["x-trace-id"]) == 32
    assert len(health.headers["x-correlation-id"]) == 36
    assert metrics.status_code == 200
    assert "http_server_requests_total" in metrics.text
    assert "http_server_duration_ms_count" in metrics.text
