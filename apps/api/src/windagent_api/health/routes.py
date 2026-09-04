"""Health and readiness probes.

``/health`` is liveness: the process is up and serving requests.  ``/ready``
is readiness: configuration validated at composition plus, when the
composition root owns a database, a live PostgreSQL probe (plan section 15
gates "PostgreSQL PASS" on readiness).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import Database, check_database_health


def _database_label(database_url: str) -> str:
    """Return the driver scheme of a URL without leaking credentials."""
    scheme = database_url.split("://", 1)[0]
    return scheme or "unknown"


def create_health_router(
    *,
    version: str,
    settings: Settings,
    database: Database | None,
) -> APIRouter:
    """Build the unversioned probe surface shared by every deployment."""
    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def health() -> JSONResponse:
        """Liveness probe: the process is up and serving requests."""
        return JSONResponse({"status": "ok", "version": version})

    @router.get("/ready")
    async def ready() -> JSONResponse:
        """Readiness probe: configuration plus live database check."""
        body: dict[str, Any] = {
            "status": "ready",
            "environment": settings.environment,
            "database": _database_label(settings.database_url),
        }
        if database is not None:
            report = await check_database_health(database.engine)
            body["checks"] = {"database": report.status}
            if not report.is_healthy:
                body["status"] = "unhealthy"
                # Connection details may embed host information; they are
                # only surfaced outside production.
                if settings.environment != "production" and report.error:
                    body["error"] = report.error
                return JSONResponse(body, status_code=503)
        return JSONResponse(body)

    return router
