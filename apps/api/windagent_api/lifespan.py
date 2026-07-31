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
from windagent_api.browser_sessions import BrowserSessionService
from windagent_api.composition import ApplicationContainer

logger = logging.getLogger("windagent.api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI async contextmanager managing container lifecycle."""
    bootstrap_config = initialize_bootstrap()
    app.state.bootstrap_config = bootstrap_config
    container = ApplicationContainer(db_url=bootstrap_config.db_url)
    
    await container.bootstrap()

    # Store container in app state
    app.state.container = container
    app.state.db = container.db
    app.state.event_bus = container.event_dispatcher
    app.state.event_dispatcher = container.event_dispatcher
    app.state.task_manager = container.task_manager
    app.state.provider_registry = container.provider_registry
    app.state.tool_registry = container.tool_registry
    app.state.worker_status_query = container.worker_status_query
    app.state.browser_session_service = BrowserSessionService()

    logger.info("FastAPI lifespan startup complete.")
    try:
        yield
    finally:
        logger.info("FastAPI lifespan shutting down...")
        await app.state.browser_session_service.close_all()
        await container.shutdown()
        logger.info("FastAPI lifespan shutdown complete.")
