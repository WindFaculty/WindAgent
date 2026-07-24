"""Phase 14B — Backend Lifecycle Management."""
from __future__ import annotations

import logging
from typing import Any

from bootstrap.container import ApplicationContainer

log = logging.getLogger("windagent.backend.lifecycle")


async def shutdown_container(container: ApplicationContainer) -> None:
    """Orderly shutdown of container-managed resources."""
    log.info("shutting down application container resources")

    # 1. Close browser sessions if present
    if hasattr(container, "browser_service") and container.browser_service:
        try:
            await container.browser_service.close_all()
        except Exception:
            log.exception("error closing browser service")

    # 2. Shutdown orchestration container
    if container.orchestration_container and hasattr(container.orchestration_container, "shutdown"):
        try:
            await container.orchestration_container.shutdown()
        except Exception:
            log.exception("error shutting down orchestration container")

    # 3. Dispose DB handles
    if container.db:
        try:
            await container.db.dispose()
        except Exception:
            log.exception("error disposing database")
