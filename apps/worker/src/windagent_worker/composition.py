"""Module-runtime adapter for the worker composition root."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from windagent.platform.jobs import JobHandler, JobHandlerRegistry
from windagent.platform.modules import (
    CommandRegistration,
    EventHandlerRegistration,
    JobRegistration,
    QueryRegistration,
)


@dataclass(slots=True)
class WorkerModuleRuntime:
    """Receive manifests without hard-coding feature names in the worker."""

    jobs: JobHandlerRegistry
    commands: list[CommandRegistration] = field(default_factory=list, init=False)
    queries: list[QueryRegistration] = field(default_factory=list, init=False)
    event_handlers: list[EventHandlerRegistration] = field(default_factory=list, init=False)
    routers: list[tuple[str, object]] = field(default_factory=list, init=False)
    migrations: list[tuple[str, object]] = field(default_factory=list, init=False)

    def register_command(self, registration: CommandRegistration) -> None:
        self.commands.append(registration)

    def register_query(self, registration: QueryRegistration) -> None:
        self.queries.append(registration)

    def register_job(self, registration: JobRegistration) -> None:
        handler = cast(JobHandler, registration.handler)
        self.jobs.register(handler, job_type=registration.job_type)

    def register_event_handler(self, registration: EventHandlerRegistration) -> None:
        self.event_handlers.append(registration)

    def register_router(self, module_id: str, router: object) -> None:
        self.routers.append((module_id, router))

    def register_migration(self, module_id: str, migration: object) -> None:
        self.migrations.append((module_id, migration))
