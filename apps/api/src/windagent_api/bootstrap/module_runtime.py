"""Module-runtime adapter for the API composition root."""

from __future__ import annotations

from dataclasses import dataclass, field

from windagent.platform.modules import (
    CommandRegistration,
    EventHandlerRegistration,
    InMemoryModuleRegistry,
    JobRegistration,
    QueryRegistration,
)

from .buses import InProcessCommandBus, InProcessQueryBus


@dataclass(slots=True)
class ApiModuleRuntime:
    """Receive manifests without hard-coding feature names in the API.

    Commands and queries are wired into the in-process buses; routers are
    collected for the versioned ``/api/v4`` mount.  Jobs, event handlers, and
    migrations belong to the worker or migration composition roots, so the
    API only records them for diagnostics.
    """

    command_bus: InProcessCommandBus
    query_bus: InProcessQueryBus
    module_registry: InMemoryModuleRegistry
    routers: list[tuple[str, object]] = field(default_factory=list, init=False)
    jobs: list[JobRegistration] = field(default_factory=list, init=False)
    event_handlers: list[EventHandlerRegistration] = field(
        default_factory=list, init=False
    )
    migrations: list[tuple[str, object]] = field(default_factory=list, init=False)

    def register_command(self, registration: CommandRegistration) -> None:
        self.command_bus.register(registration.command_type, registration.handler)

    def register_query(self, registration: QueryRegistration) -> None:
        self.query_bus.register(registration.query_type, registration.handler)

    def register_job(self, registration: JobRegistration) -> None:
        self.jobs.append(registration)

    def register_event_handler(self, registration: EventHandlerRegistration) -> None:
        self.event_handlers.append(registration)

    def register_router(self, module_id: str, router: object) -> None:
        self.routers.append((module_id, router))

    def register_migration(self, module_id: str, migration: object) -> None:
        self.migrations.append((module_id, migration))
