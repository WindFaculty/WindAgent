"""Phase 14B — Container and Config Validation."""
from __future__ import annotations

from bootstrap.container import ApplicationContainer


def validate_application_container(container: ApplicationContainer) -> bool:
    """Ensure container meets required startup validation requirements."""
    container.validate()
    return True
