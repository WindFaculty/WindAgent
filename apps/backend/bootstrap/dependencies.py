"""Phase 14B — Application Container FastAPI Dependencies."""
from __future__ import annotations

from fastapi import Request

from bootstrap.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    """Retrieve typed ApplicationContainer from request app state."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("ApplicationContainer has not been initialized on app.state")
    return container
