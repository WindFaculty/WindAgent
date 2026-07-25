"""
Typed FastAPI Dependency Providers for WindAgent V2 API (Phase 25 Cutover).
Provides clean dependency injection from ApplicationContainer with safe fallback for uncontextualized test runners.
"""

from __future__ import annotations
from typing import Generator, Optional
from fastapi import Request, HTTPException, status

from windagent_api.composition import ApplicationContainer
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration.task_manager.service import TaskManager
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine

_fallback_container: Optional[ApplicationContainer] = None


def get_container(request: Request) -> ApplicationContainer:
    global _fallback_container
    container = getattr(request.app.state, "container", None)
    if container is None:
        if _fallback_container is None:
            _fallback_container = ApplicationContainer()
            _fallback_container.db = DatabaseManager("sqlite+aiosqlite:///:memory:")
            _fallback_container.task_manager = TaskManager(uow_factory=_fallback_container.db.session_factory)
            _fallback_container.provider_registry = CanonicalModelRegistryService()
            _fallback_container.tool_registry = ToolRegistry()
            _fallback_container.execution_registry = ExecutionRuntimeRegistry()
            _fallback_container.is_initialized = True
        container = _fallback_container
        request.app.state.container = container
    return container


def get_uow(request: Request) -> SqlUnitOfWork:
    container = get_container(request)
    return container.get_uow()


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
