"""Operational telemetry transport surfaces."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from windagent.platform.observability import MetricsExporter, Telemetry


def create_metrics_router(telemetry: Telemetry) -> APIRouter:
    """Expose a scrape endpoint without request payloads or secret values."""
    if not isinstance(telemetry, MetricsExporter):
        raise TypeError("telemetry must implement MetricsExporter")
    exporter = telemetry
    router = APIRouter(tags=["observability"])

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            exporter.render_prometheus(),
            media_type="text/plain; version=0.0.4",
        )

    return router
