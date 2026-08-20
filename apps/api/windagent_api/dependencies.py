"""
Typed FastAPI Dependency Providers for WindAgent V2 API (Phase 25 Cutover).
Provides clean dependency injection from ApplicationContainer with safe fallback for uncontextualized test runners.

Phase 7: the no-lifespan fallback drives the canonical ApplicationContainer
composers (``bootstrap``) instead of hand-composing a second service graph.
Dependency getters return composed services or fail closed; they never lazily
create new authority/runtime instances.
"""

from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import Request

from windagent_api.composition import ApplicationContainer
from windagent_orchestration.task_manager.service import TaskManager
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_orchestration.orchestrator_service import OrchestratorService

_container: Optional[ApplicationContainer] = None
_db_path: Optional[Path] = None


def _build_container() -> ApplicationContainer:
    """Uncontextualized (no-lifespan) test runner fallback with a real file DB + schema.

    Uses the canonical ApplicationContainer composers (``bootstrap``) so the
    fallback graph is identical to the lifespan graph.  It may synchronously
    drive the async bootstrap for the no-lifespan TestClient fallback, but it
    never hand-composes runtime/provider/realtime/storage authorities again.
    """
    global _db_path
    _db_path = Path(tempfile.mkdtemp(prefix="windagent_fb_")) / "fallback.db"
    db_url = f"sqlite+aiosqlite:///{_db_path}"
    container = ApplicationContainer(db_url=db_url)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(container.bootstrap())
        # Phase 4: the demo seed is opt-in (WINDAGENT_PROFILE=demo); default
        # startup never installs demo records.
        if os.getenv("WINDAGENT_PROFILE", "").lower() == "demo":
            loop.run_until_complete(container.seed_demo_profile())
    finally:
        loop.close()
    return container


def get_container(request: Request) -> ApplicationContainer:
    global _container
    container = getattr(request.app.state, "container", None)
    if container is None:
        if _container is None:
            _container = _build_container()
        container = _container
        request.app.state.container = container
    return container


async def get_uow(request: Request):
    """Returns a UnitOfWork with active session and repositories."""
    container = get_container(request)
    async with container.get_uow() as uow:
        yield uow


def get_task_manager(request: Request) -> TaskManager:
    container = get_container(request)
    if container.task_manager is None:
        raise RuntimeError("TaskManager is not composed.")
    return container.task_manager


def get_orchestrator_service(request: Request) -> OrchestratorService:
    container = get_container(request)
    if container.orchestrator_service is None:
        raise RuntimeError("OrchestratorService is not composed.")
    return container.orchestrator_service


def get_provider_registry(request: Request) -> CanonicalModelRegistryService:
    container = get_container(request)
    if container.provider_registry is None:
        raise RuntimeError("CanonicalModelRegistryService is not composed.")
    return container.provider_registry


def get_tool_registry(request: Request) -> ToolRegistry:
    container = get_container(request)
    if container.tool_registry is None:
        raise RuntimeError("ToolRegistry is not composed.")
    return container.tool_registry


def get_permission_engine(request: Request) -> PermissionEngine:
    return PermissionEngine()


def get_video_production_uow(request: Request):
    from windagent_storage.unit_of_work.video_production_uow import VideoProductionUnitOfWork
    container = get_container(request)
    return VideoProductionUnitOfWork(container.db.session_factory)


def get_v3_resource_service(request: Request):
    """Returns the namespaced durable V3 resource application service."""
    container = get_container(request)
    if container.v3_resource_service is None:
        raise RuntimeError("V3ResourceService is not composed.")
    return container.v3_resource_service


def get_route_lock_service(request: Request) -> RouteLockService:
    """Returns the composed RouteLockService (production lock authority)."""
    container = get_container(request)
    if container.route_lock_service is None:
        raise RuntimeError("RouteLockService is not composed.")
    return container.route_lock_service


def get_routing_authority_bridge(request: Request):
    """Returns the routing authority bridge (SQL rules -> runtime ruleset)."""
    container = get_container(request)
    if container.routing_authority_bridge is None:
        raise RuntimeError("RoutingAuthorityBridge is not composed.")
    return container.routing_authority_bridge


def get_provider_management_service(request: Request):
    """Returns the composed provider-management service (Phase 10)."""
    container = get_container(request)
    if container.provider_management_service is None:
        raise RuntimeError("ProviderManagementService is not composed.")
    return container.provider_management_service


def get_provider_probe_service(request: Request):
    """Returns the composed provider probe service (Phase 10)."""
    container = get_container(request)
    if container.provider_probe_service is None:
        raise RuntimeError("ProviderProbeService is not composed.")
    return container.provider_probe_service