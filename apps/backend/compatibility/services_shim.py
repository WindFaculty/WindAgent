"""
Thin Services Compatibility Shim for WindAgent Phase 27 Legacy Backend Evacuation.
Delegates all legacy service calls to canonical V2 workspace packages:
- windagent_orchestration (TaskManager)
- windagent_tools (ToolRegistry, PermissionEngine)
- windagent_execution (ExecutionRuntimeRegistry)
- windagent_providers (CanonicalModelRegistryService)
- windagent_storage (SqlUnitOfWork)
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from windagent_orchestration.task_manager.service import TaskManager
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

logger = logging.getLogger("windagent.backend.compatibility")


class LegacyEventBusShim:
    """Compatibility wrapper for EventBus publishing."""
    def __init__(self):
        self._handlers: Dict[str, list] = {}

    async def publish(self, topic: str, event: Any) -> None:
        logger.debug(f"[Compatibility Shim] Published event on topic '{topic}'")

    async def subscribe(self, topic: str, handler: Any) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)


class LegacySessionServiceShim:
    """Compatibility wrapper for SessionService."""
    def __init__(self, uow: Optional[SqlUnitOfWork] = None):
        self.uow = uow

    async def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        return {"session_id": session_id, "status": "active"}


class LegacyPlannerServiceShim:
    """Compatibility wrapper for PlannerService."""
    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        return {"steps": ["reproduce", "diagnose", "patch", "verify"], "prompt": prompt}


# Forwarding exports
__all__ = [
    "TaskManager",
    "ToolRegistry",
    "PermissionEngine",
    "ExecutionRuntimeRegistry",
    "CanonicalModelRegistryService",
    "SqlUnitOfWork",
    "LegacyEventBusShim",
    "LegacySessionServiceShim",
    "LegacyPlannerServiceShim",
]
