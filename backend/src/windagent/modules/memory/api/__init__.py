"""HTTP API package for the Memory bounded context."""

from .routes import (
    MODULE_ID,
    MODULE_VERSION,
    PREFIX,
    create_memory_router,
)

__all__ = [
    "MODULE_ID",
    "MODULE_VERSION",
    "PREFIX",
    "create_memory_router",
]
