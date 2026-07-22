"""
FastAPI entrypoint for WindAgent Architecture V2 API.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="WindAgent V2 API",
    description="Modular Monolith API V2 Skeleton",
    version="0.3.0",
)


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
