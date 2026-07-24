"""Phase 14B — Application Factory & Bootstrap Module."""
from __future__ import annotations

from bootstrap.container import ApplicationContainer
from bootstrap.dependencies import get_container
from bootstrap.lifecycle import shutdown_container
from bootstrap.validation import validate_application_container

__all__ = [
    "ApplicationContainer",
    "get_container",
    "shutdown_container",
    "validate_application_container",
]
