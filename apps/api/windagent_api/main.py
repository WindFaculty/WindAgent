"""
FastAPI entrypoint for WindAgent Architecture V2 API.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from windagent_api.routers.v2_tasks import router as v2_tasks_router
from windagent_api.routers.v2_runs import router as v2_runs_router
from windagent_api.routers.v2_workflows import router as v2_workflows_router
from windagent_api.routers.v2_events import router as v2_events_router
from windagent_api.routers.v2_providers import router as v2_providers_router
from windagent_api.routers.v2_tools import router as v2_tools_router
from windagent_api.routers.v2_permissions import router as v2_permissions_router
from windagent_api.routers.v2_artifacts import router as v2_artifacts_router
from windagent_api.routers.v2_evals import router as v2_evals_router
from windagent_api.routers.compatibility import v1_router, parity_router

app = FastAPI(
    title="WindAgent V2 API",
    description="Modular Monolith API V2 Production Application",
    version="0.3.0",
)

# Register V2 Routers
app.include_router(v2_tasks_router)
app.include_router(v2_runs_router)
app.include_router(v2_workflows_router)
app.include_router(v2_events_router)
app.include_router(v2_providers_router)
app.include_router(v2_tools_router)
app.include_router(v2_permissions_router)
app.include_router(v2_artifacts_router)
app.include_router(v2_evals_router)

# Register V1 Compatibility and Parity Matrix Routers
app.include_router(v1_router)
app.include_router(parity_router)


class HealthResponse(BaseModel):
    status: str
    service: str


class ArchitectureResponse(BaseModel):
    architecture: str
    status: str
    version: str


@app.get("/health/live", response_model=HealthResponse)
async def health_live() -> HealthResponse:
    return HealthResponse(status="live", service="windagent-api")


@app.get("/health/ready", response_model=HealthResponse)
async def health_ready() -> HealthResponse:
    return HealthResponse(status="ready", service="windagent-api")


@app.get("/internal/architecture", response_model=ArchitectureResponse)
async def internal_architecture() -> ArchitectureResponse:
    return ArchitectureResponse(
        architecture="V2",
        status="scaffold",
        version="0.3.0",
    )
