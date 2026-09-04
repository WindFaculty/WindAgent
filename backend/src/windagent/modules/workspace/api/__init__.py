"""Workspace API package."""

from .routes import (
    MODULE_ID,
    MODULE_VERSION,
    WORKSPACES_PREFIX,
    create_workspace_router,
)

__all__ = [
    "MODULE_ID",
    "MODULE_VERSION",
    "WORKSPACES_PREFIX",
    "create_workspace_router",
]
