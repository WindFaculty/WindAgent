"""
Typed FastAPI Dependency Providers for WindAgent V2 API (Phase 25 Cutover).
Provides clean dependency injection from ApplicationContainer with safe fallback for uncontextualized test runners.
"""

from __future__ import annotations
import asyncio
import tempfile
from pathlib import Path
from typing import Generator, Optional
from fastapi import Request, HTTPException, status

from windagent_api.composition import ApplicationContainer
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration.task_manager.service import TaskManager
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine

_fallback_container: Optional[ApplicationContainer] = None
_fallback_db_path: Optional[Path] = None


def _build_fallback_container() -> ApplicationContainer:
    """Uncontextualized (no-lifespan) test runner fallback with a real file DB + schema."""
    global _fallback_db_path
    _fallback_db_path = Path(tempfile.mkdtemp(prefix="windagent_fb_")) / "fallback.db"
    db_url = f"sqlite+aiosqlite:///{_fallback_db_path}"
    container = ApplicationContainer()
    container.db = DatabaseManager(db_url)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(container.db.create_tables(BaseORM.metadata))
    finally:
        loop.close()
    container.task_manager = TaskManager(uow_factory=container.db.session_factory)
    container.task_submission = SqlWorkSubmissionAdapter(container.db.session_factory)
    container.provider_registry = CanonicalModelRegistryService()
    container.tool_registry = ToolRegistry()
    container.execution_registry = ExecutionRuntimeRegistry()
    container.is_initialized = True
    return container


def get_container(request: Request) -> ApplicationContainer:
    global _fallback_container
    container = getattr(request.app.state, "container", None)
    if container is None:
        if _fallback_container is None:
            _fallback_container = _build_fallback_container()
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
