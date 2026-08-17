"""
FastAPI entrypoint for WindAgent Architecture V2 API (Phase 25 Cutover).
Uses canonical lifespan manager, ApplicationContainer composition root, RFC 7807 exception mapping for WindAgentError,
and registers all canonical V2 routers. API V1 has been permanently removed - returns 410 Gone.
"""

from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from windagent_core.errors.exceptions import (
    WindAgentError, NotFoundError, PermissionDeniedError, ValidationError, DomainError
)
from windagent_core.version import (
    PRODUCT_VERSION,
    ARCHITECTURE_GENERATION,
    API_VERSION,
    PROVIDER_PROTOCOL_VERSION,
    ARTIFACT_PROTOCOL_VERSION,
)
from windagent_api.lifespan import lifespan
from windagent_api.health import router as health_router
from windagent_api.routers.v2_sessions import router as v2_sessions_router
from windagent_api.routers.v2_tasks import router as v2_tasks_router
from windagent_api.routers.v2_runs import router as v2_runs_router
from windagent_api.routers.v2_workflows import router as v2_workflows_router
from windagent_api.routers.v2_events import v2_events_router
from windagent_api.routers.v2_events import v2_events_legacy_router
from windagent_api.routers.v2_providers import router as v2_providers_router
from windagent_api.routers.v2_tools import router as v2_tools_router
from windagent_api.routers.v2_permissions import router as v2_permissions_router
from windagent_api.routers.v2_artifacts import router as v2_artifacts_router
from windagent_api.routers.v2_memory import router as v2_memory_router
from windagent_api.routers.v2_plugins import router as v2_plugins_router
from windagent_api.routers.v2_skills import router as v2_skills_router
from windagent_api.routers.v2_evals import router as v2_evals_router
from windagent_api.routers.v2_observability import router as v2_observability_router
from windagent_api.routers.v2_browser import router as v2_browser_router
from windagent_api.routers.v2_production_workspace import router as v2_production_workspace_router
from windagent_api.routers.v2_screenplay_workspace import router as v2_screenplay_workspace_router
from windagent_api.routers.v2_assets import router as v2_assets_router
from windagent_api.routers.v2_collaboration import router as v2_collaboration_router
from windagent_api.routers.v2_conversations import router as v2_conversations_router
from windagent_api.routers.v2_conflict_recovery import router as v2_conflict_recovery_router

from windagent_api.routers.conversation_streams import router as conversation_streams_router
from windagent_api.routers.v3 import v3_router
from windagent_api.routers.v3.common import (
    CorrelationIdMiddleware,
    ApiProblemException,
    api_problem_exception_handler,
)
from windagent_api.routers.v3.studio.errors import studio_error_handler
from windagent_core.contracts.studio.errors import StudioError

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("windagent.api.main")

app = FastAPI(
    title="WindAgent API",
    description="Modular Monolith API Production Application with Unified V3 Foundation",
    version=PRODUCT_VERSION,
    lifespan=lifespan,
)

# Correlation ID tracing middleware (P2.5)
app.add_middleware(CorrelationIdMiddleware)

# CORS configuration for Web and Desktop Frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers Mapping WindAgentError to Structured JSON
@app.exception_handler(ApiProblemException)
async def v3_problem_exception_handler(request: Request, exc: ApiProblemException) -> JSONResponse:
    return await api_problem_exception_handler(request, exc)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "type": "https://windagent.io/errors/not-found",
            "title": "Resource Not Found",
            "status": 404,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_NOT_FOUND"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_exception_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "type": "https://windagent.io/errors/permission-denied",
            "title": "Permission Denied",
            "status": 403,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_PERMISSION_DENIED"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "type": "https://windagent.io/errors/validation-error",
            "title": "Validation Error",
            "status": 400,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_VALIDATION_FAILED"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(DomainError)
async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "https://windagent.io/errors/domain-error",
            "title": "Domain Error",
            "status": 422,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_DOMAIN_INVARIANT_VIOLATION"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(StudioError)
async def studio_exception_handler(request: Request, exc: StudioError) -> JSONResponse:
    return studio_error_handler(request, exc)


@app.exception_handler(WindAgentError)
async def base_windagent_exception_handler(request: Request, exc: WindAgentError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "type": "https://windagent.io/errors/internal",
            "title": "WindAgent Internal Error",
            "status": 500,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_INTERNAL"),
        },
    )


# Register Health Router
app.include_router(health_router)

# Register Canonical V2 Routers
app.include_router(v2_sessions_router)
app.include_router(v2_tasks_router)
app.include_router(v2_runs_router)
app.include_router(v2_workflows_router)
app.include_router(v2_events_router)
app.include_router(v2_events_legacy_router)
app.include_router(v2_providers_router)
app.include_router(v2_tools_router)
app.include_router(v2_permissions_router)
app.include_router(v2_artifacts_router)
app.include_router(v2_memory_router)
app.include_router(v2_plugins_router)
app.include_router(v2_skills_router)
app.include_router(v2_evals_router)
app.include_router(v2_observability_router)
app.include_router(v2_browser_router)
app.include_router(v2_production_workspace_router)
app.include_router(v2_screenplay_workspace_router)
app.include_router(v2_assets_router)
app.include_router(v2_collaboration_router)
app.include_router(v2_conversations_router)
app.include_router(v2_conflict_recovery_router)

app.include_router(conversation_streams_router)

# Unified V3 Root Router (Plan C1 + Phase 2 Foundation)
app.include_router(v3_router)


# V2 deprecation metadata: additive headers only. V2 is not removed or
# redirected; clients learn the successor surface without behavior change.
@app.middleware("http")
async def v2_deprecation_metadata(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v2"):
        response.headers["Deprecation"] = "true"
        response.headers["X-WindAgent-Deprecation"] = "v2"
        # Only claim specific successor when domain replacement exists (P2.10)
        if request.url.path.startswith("/api/v2/screenplay_workspace") or request.url.path.startswith("/api/v2/production_workspace"):
            response.headers["X-WindAgent-Successor"] = "/api/v3/studio"
    return response


# API V1 Tombstone Handler - Returns 410 Gone for all /api/v1/* requests
@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def api_v1_tombstone(request: Request, path: str):
    """
    API V1 has been permanently removed as per Architecture V2 cutover.
    This tombstone handler returns 410 Gone to indicate the resource is no longer available.
    """
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "type": "https://windagent.io/errors/api-v1-removed",
            "title": "API V1 Removed",
            "status": 410,
            "detail": "API V1 has been permanently removed. Please migrate to API V2.",
            "removal_date": "2026-07-25",
            "migration_guide": "https://windagent.io/docs/architecture-v2-migration",
            "available_endpoints": "/api/v2/*",
        },
    )


class ArchitectureResponse(BaseModel):
    architecture: str
    status: str
    version: str
    architecture_generation: str
    api_version: str
    provider_protocol_version: str
    artifact_protocol_version: str


@app.get("/internal/architecture", response_model=ArchitectureResponse)
async def internal_architecture() -> ArchitectureResponse:
    return ArchitectureResponse(
        architecture="V2",
        status="canonical_api_v2_production",
        version=PRODUCT_VERSION,
        architecture_generation=ARCHITECTURE_GENERATION,
        api_version=API_VERSION,
        provider_protocol_version=PROVIDER_PROTOCOL_VERSION,
        artifact_protocol_version=ARTIFACT_PROTOCOL_VERSION,
    )
