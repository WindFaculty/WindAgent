"""Registration target owned by an application's composition root."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .manifest import (
    CommandRegistration,
    EventHandlerRegistration,
    JobRegistration,
    QueryRegistration,
)


@runtime_checkable
class ModuleRuntime(Protocol):
    """Receives validated module contributions in a fixed bootstrap order.

    Concrete API, worker, and migration composition roots implement this seam.
    No module is allowed to reach into those roots directly.
    """

    def register_command(self, registration: CommandRegistration) -> None:
        """Register one command handler."""

    def register_query(self, registration: QueryRegistration) -> None:
        """Register one query handler."""

    def register_job(self, registration: JobRegistration) -> None:
        """Register one job handler."""

    def register_event_handler(self, registration: EventHandlerRegistration) -> None:
        """Register one event handler."""

    def register_router(self, module_id: str, router: object) -> None:
        """Register one transport router owned by ``module_id``."""

    def register_migration(self, module_id: str, migration: object) -> None:
        """Register one migration owned by ``module_id``."""
