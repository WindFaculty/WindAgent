"""
Canonical FastAPI Lifespan Manager for WindAgent V2 API (Phase 16).
Controls application startup and shutdown hooks via ApplicationContainer.
"""

from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from windagent_api.bootstrap import initialize_bootstrap
from windagent_api.composition import ApplicationContainer

logger = logging.getLogger("windagent.api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI async contextmanager managing container lifecycle."""
    bootstrap_config = initialize_bootstrap()
    container = ApplicationContainer(db_url=bootstrap_config.db_url)
    
    await container.bootstrap()

    # Store container in app state
    app.state.container = container
    app.state.db = container.db
    app.state.event_bus = container.event_bus
    app.state.task_manager = container.task_manager
    app.state.orchestration_container = container.orchestration_container
    app.state.provider_registry = container.provider_registry
    app.state.tool_registry = container.tool_registry

    logger.info("FastAPI lifespan startup complete.")
    try:
        yield
    finally:
        logger.info("FastAPI lifespan shutting down...")
        await container.shutdown()
        logger.info("FastAPI lifespan shutdown complete.")
