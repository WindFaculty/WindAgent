"""Quality API package."""

from .routes import (
    MODULE_ID,
    MODULE_VERSION,
    QUALITY_PREFIX,
    create_quality_router,
)

__all__ = [
    "MODULE_ID",
    "MODULE_VERSION",
    "QUALITY_PREFIX",
    "create_quality_router",
]
