"""
V3 Studio shared dependencies (Plan C1).

Idempotency rule: every mutating endpoint requires a non-blank
``X-Idempotency-Key`` header (frozen errors.json idempotency_rule). Expected
revision/version/hash travel in the request body. The actor is taken from
``X-WindAgent-Actor`` and defaults to ``system``; the same security policy as
V2 applies to V3 (no new auth boundary is introduced here).
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, Request

from windagent_api.dependencies import get_container
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.errors import StudioCapabilityUnavailableError, StudioValidationError


def get_studio_application_service(request: Request) -> StudioApplicationService:
    """Resolve the composed Studio application service from the container.

    The container always composes the service object; its Plan A ports are
    wired at A handoff. If the container is unavailable the API fails closed
    with CAPABILITY_UNAVAILABLE instead of inventing a fallback.
    """
    container = get_container(request)
    service = getattr(container, "studio_application_service", None)
    if service is None:
        raise StudioCapabilityUnavailableError(
            "Studio application service is not composed.",
            details={"missing": "studio_application_service"},
        )
    return service


def require_idempotency_key(
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
) -> str:
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise StudioValidationError(
            "X-Idempotency-Key header is required for Studio mutating commands.",
            details={"field": "X-Idempotency-Key"},
        )
    return x_idempotency_key.strip()


def get_actor(
    x_windagent_actor: Optional[str] = Header(default=None, alias="X-WindAgent-Actor"),
) -> str:
    actor = (x_windagent_actor or "").strip()
    return actor or "system"


__all__ = ["get_studio_application_service", "require_idempotency_key", "get_actor"]
