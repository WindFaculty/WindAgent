"""Phase 14B — Typed Backend Application Container."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from db.database import Database
from services.event_bus import EventBus
from services.permission_service import PermissionService
from services.planner_service import PlannerService
from services.route_lock_service import RouteLockService
from services.session_service import SessionService


@dataclass
class ApplicationContainer:
    """Typed container holding backend core runtime services."""

    db: Database
    event_bus: EventBus
    session_service: SessionService
    permission_service: PermissionService
    planner_service: PlannerService
    route_lock_service: RouteLockService
    workflow_service: Any
    workflow_runner: Any
    orchestration_container: Any
    recovery_service: Any

    def validate(self) -> None:
        """Validate all required dependencies are non-null and valid."""
        for field_name in (
            "db",
            "event_bus",
            "session_service",
            "permission_service",
            "planner_service",
            "route_lock_service",
        ):
            val = getattr(self, field_name, None)
            if val is None:
                raise ValueError(f"Required dependency '{field_name}' is missing in ApplicationContainer")
