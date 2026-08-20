"""
Canonical FastAPI Lifespan Manager for WindAgent V2 API (Phase 16).
Controls application startup and shutdown hooks via ApplicationContainer.
"""

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from windagent_api.bootstrap import initialize_bootstrap
from windagent_api.browser_sessions import BrowserSessionService
from windagent_api.composition import ApplicationContainer

logger = logging.getLogger("windagent.api.lifespan")


def _demo_profile_enabled() -> bool:
    """True only when the explicit demo profile is requested.

    Phase 4: demo seeding is opt-in. Default development/test/production
    startup must never silently install demo records.
    """
    return os.getenv("WINDAGENT_PROFILE", "").lower() == "demo"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI async contextmanager managing container lifecycle."""
    bootstrap_config = initialize_bootstrap()
    app.state.bootstrap_config = bootstrap_config
    container = ApplicationContainer(db_url=bootstrap_config.db_url)
    
    await container.bootstrap()

    # Phase 6: start the canonical realtime hub (single read-only SQL fallback
    # loop) before serving traffic; it is stopped before database shutdown.
    if container.realtime_hub is not None:
        await container.realtime_hub.start()

    # Phase 4: install the demo seed profile ONLY when explicitly requested via
    # WINDAGENT_PROFILE=demo. Default development/test/production startup never
    # silently installs demo records. The container owns the seeding operation
    # (including canonical-model persistence and the routing-rules refresh) so
    # lifespan never imports storage/database.
    if _demo_profile_enabled():
        await container.seed_demo_profile()

    # Store container in app state
    app.state.container = container
    app.state.db = container.db
    app.state.event_bus = container.event_dispatcher
    app.state.event_dispatcher = container.event_dispatcher
    app.state.log_service = container.log_service
    app.state.task_manager = container.task_manager
    app.state.provider_registry = container.provider_registry
    app.state.tool_registry = container.tool_registry
    app.state.worker_status_query = container.worker_status_query
    app.state.orchestrator_service = container.orchestrator_service
    app.state.release_telemetry = container.release_telemetry
    app.state.browser_session_service = BrowserSessionService()

    logger.info("FastAPI lifespan startup complete.")
    try:
        yield
    finally:
        logger.info("FastAPI lifespan shutting down...")
        await app.state.browser_session_service.close_all()
        # The container owns the realtime hub lifecycle: container.shutdown()
        # stops the hub (and unsubscribes it from the dispatcher) before the
        # database is closed.  No redundant stop call here.
        await container.shutdown()
        logger.info("FastAPI lifespan shutdown complete.")
