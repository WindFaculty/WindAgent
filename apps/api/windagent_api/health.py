"""
Canonical Health Liveness and Readiness Probe Router for WindAgent V2 API (Phase 10).
Provides real health checks using HealthChecker service from observability module.
All checks are real, no hardcoded values. Implements profile-based behavior.
"""

from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import JSONResponse

from windagent_observability.health import (
    HealthChecker,
    HealthProfile,
    HealthStatus,
)

logger = logging.getLogger("windagent.api.health")
router = APIRouter(prefix="/health", tags=["health"])


def get_health_checker(request: Request) -> HealthChecker:
    """Dependency to get or create HealthChecker instance."""
    if not hasattr(request.app.state, "_health_checker"):
        container = getattr(request.app.state, "container", None)
        db = getattr(request.app.state, "db", container.db if container else None)
        bootstrap_config = getattr(request.app.state, "bootstrap_config", None)
        
        # Determine profile from config
        profile_str = getattr(bootstrap_config, "env", "development")
        profile = HealthProfile(profile_str) if profile_str in ["production", "development", "test"] else HealthProfile.DEVELOPMENT
        
        # Create HealthChecker with real dependencies
        db_session_factory = db.session_factory if db else None
        worker_status_query = getattr(container, "worker_status_query", None) if container else None
        provider_registry = getattr(container, "provider_registry", None) if container else None
        tool_registry = getattr(container, "tool_registry", None) if container else None
        plugin_registry = getattr(container, "plugin_registry", None) if container else None
        skill_registry = getattr(container, "skill_registry", None) if container else None
        workflow_registry = getattr(container, "workflow_registry", None) if container else None
        event_dispatcher = getattr(request.app.state, "event_bus", getattr(container, "event_dispatcher", None) if container else None)
        
        request.app.state._health_checker = HealthChecker(
            db_session_factory=db_session_factory,
            worker_status_query=worker_status_query,
            provider_registry=provider_registry,
            tool_registry=tool_registry,
            plugin_registry=plugin_registry,
            skill_registry=skill_registry,
            workflow_registry=workflow_registry,
            event_dispatcher=event_dispatcher,
            expected_schema_head=getattr(container, "expected_schema_head", None) if container else None,
            profile=profile,
        )
    
    return request.app.state._health_checker


@router.get("")
@router.get("/")
async def health_root() -> Dict[str, str]:
    return {"status": "ok", "service": "windagent-api"}


@router.get("/live")
async def health_liveness(
    checker: HealthChecker = Depends(get_health_checker),
) -> Dict[str, str]:
    """
    Process liveness probe.
    Only confirms process event loop is alive.
    Does NOT check external dependencies.
    """
    is_alive = await checker.check_liveness()
    status_value = "live" if is_alive else "not_live"
    return {"status": status_value, "service": "windagent-api"}


@router.get("/ready")
async def health_readiness(
    request: Request,
    checker: HealthChecker = Depends(get_health_checker),
) -> Dict[str, Any]:
    """
    Real readiness probe checking all required components.
    
    Checks (all real, no hardcoded values):
    - Database connection
    - Current schema revision
    - Outbox publisher heartbeat
    - Queue access
    - Worker heartbeat
    - Provider registry loaded
    - Tool registry loaded
    - Plugin registry loaded
    - Skill registry loaded
    - Workflow registry loaded
    - Event dispatcher active
    - Required filesystem paths
    - Configuration validity
    
    Profile-based behavior:
    - PRODUCTION: Fail-closed, returns 503 if any required check fails
    - DEVELOPMENT: Worker not running returns DEGRADED (not UP)
    - TEST: Allows in-memory adapters when explicitly injected
    """
    bootstrap_config = getattr(request.app.state, "bootstrap_config", None)
    profile_str = getattr(bootstrap_config, "env", "development")
    
    # Map string to HealthProfile
    profile = HealthProfile(profile_str) if profile_str in ["production", "development", "test"] else HealthProfile.DEVELOPMENT
    
    if not isinstance(checker, HealthChecker):
        checker = get_health_checker(request)

    # Profile-based readiness check
    readiness_status = await checker.check_readiness(profile)
    
    # Convert to response format
    checks_dict = {}
    for name, check_result in readiness_status.checks.items():
        checks_dict[name] = {
            "status": check_result.status.value,
            "message": check_result.message,
            "required": check_result.required,
            "details": check_result.details,
        }
    
    overall_status = readiness_status.overall_status.value
    res = {
        "status": overall_status,
        "service": "windagent-api",
        "profile": profile.value,
        "checks": checks_dict,
    }
    
    # Fail-closed: if overall status is not UP, return 503
    if readiness_status.overall_status != HealthStatus.UP:
        logger.warning(f"Readiness check failed with status: {overall_status}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=res,
        )
    
    return res
