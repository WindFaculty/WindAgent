"""
Typed FastAPI Dependency Providers for WindAgent V2 API (Phase 25 Cutover).
Provides clean dependency injection from ApplicationContainer with safe fallback for uncontextualized test runners.
"""

from __future__ import annotations
import asyncio
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import Request

from windagent_api.composition import ApplicationContainer
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.security.encryption import decrypt
from windagent_orchestration.task_manager.service import TaskManager
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_orchestration.orchestrator_service import OrchestratorService
from windagent_providers.routing.endpoint_adapter_resolver import EndpointAdapterResolver
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator

_container: Optional[ApplicationContainer] = None
_db_path: Optional[Path] = None


def _build_container() -> ApplicationContainer:
    """Uncontextualized (no-lifespan) test runner fallback with a real file DB + schema."""
    global _db_path
    _db_path = Path(tempfile.mkdtemp(prefix="windagent_fb_")) / "fallback.db"
    db_url = f"sqlite+aiosqlite:///{_db_path}"
    container = ApplicationContainer(db_url=db_url)
    container.db = DatabaseManager(db_url)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(container.db.upgrade_to_head(BaseORM.metadata))
    finally:
        loop.close()
    container.task_manager = TaskManager(uow_factory=container.db.session_factory)
    container.task_submission = SqlWorkSubmissionAdapter(container.db.session_factory)
    from windagent_storage.database.sync_factory import make_sync_session_factory
    from windagent_storage.repositories.v3_routing_repositories import (
        SQLEndpointBindingRepository,
        SQLProviderRoutingAuditRepository,
    )
    from windagent_storage.repositories.v3_repositories import (
        SQLEndpointRegistryRepository,
        SQLEndpointStateRepository,
        SQLQuotaStateRepository,
        SQLRouteAttemptRepository,
        SQLRouteLockRepository,
    )
    sync_factory = make_sync_session_factory(container.db_url)
    container.provider_registry = CanonicalModelRegistryService(
        binding_repository=SQLEndpointBindingRepository(sync_factory())
    )
    from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
    container.route_lock_service = RouteLockService(
        ruleset=RoutingRuleSet(
            rules=[
                RoutingRule(
                    rule_id="orchestrator-local-agent",
                    rule_version=1,
                    canonical_model_id="windagent/local-agent",
                    description="Phase-2 conversation control plane",
                )
            ]
        ),
        lock_repository=SQLRouteLockRepository(sync_factory()),
        audit_repository=SQLProviderRoutingAuditRepository(sync_factory()),
    )
    container.tool_registry = ToolRegistry()
    container.execution_registry = ExecutionRuntimeRegistry()
    container.provider_execution_coordinator = EndpointExecutionCoordinator(
        adapter_resolver=EndpointAdapterResolver(decrypt),
        endpoint_registry=SQLEndpointRegistryRepository(sync_factory()),
        endpoint_state=SQLEndpointStateRepository(sync_factory()),
        quota_state=SQLQuotaStateRepository(sync_factory()),
        attempt_log=SQLRouteAttemptRepository(sync_factory()),
    )
    container.orchestrator_service = OrchestratorService(
        container.db.session_factory,
        container.execution_registry,
        container.route_lock_service,
        container.provider_execution_coordinator,
    )
    container.is_initialized = True
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
    if not container.task_manager:
        container.task_manager = TaskManager(uow_factory=container.db.session_factory if container.db else None)
    return container.task_manager


def get_execution_registry(request: Request) -> ExecutionRuntimeRegistry:
    container = get_container(request)
    if not container.execution_registry:
        container.execution_registry = ExecutionRuntimeRegistry()
    return container.execution_registry


def get_orchestrator_service(request: Request) -> OrchestratorService:
    container = get_container(request)
    if not container.orchestrator_service:
        container.execution_registry = container.execution_registry or ExecutionRuntimeRegistry()
        container.orchestrator_service = OrchestratorService(
            container.db.session_factory,
            container.execution_registry,
            container.route_lock_service,
            container.provider_execution_coordinator,
        )
    return container.orchestrator_service


def get_provider_registry(request: Request) -> CanonicalModelRegistryService:
    container = get_container(request)
    if not container.provider_registry:
        container.provider_registry = CanonicalModelRegistryService()
    return container.provider_registry


def get_tool_registry(request: Request) -> ToolRegistry:
    container = get_container(request)
    if not container.tool_registry:
        container.tool_registry = ToolRegistry()
    return container.tool_registry


def get_permission_engine(request: Request) -> PermissionEngine:
    return PermissionEngine()


def get_video_production_uow(request: Request):
    from windagent_storage.unit_of_work.video_production_uow import VideoProductionUnitOfWork
    container = get_container(request)
    return VideoProductionUnitOfWork(container.db.session_factory)
