"""Module runtime: service composition and ambient scope for Memory (Phase 14)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from ..domain.models import RetentionPolicy
from ..domain.policy import MemoryWritePolicy
from .ports import MemoryScopeFactory
from .services import MemoryService


@dataclass(frozen=True, slots=True)
class MemoryServices:
    scope_factory: MemoryScopeFactory
    write_policy: MemoryWritePolicy = field(default_factory=MemoryWritePolicy)
    retention_policy: RetentionPolicy = field(default_factory=RetentionPolicy)


_SERVICES: ContextVar[MemoryServices | None] = ContextVar("memory_services", default=None)


@contextmanager
def bind_services(services: MemoryServices) -> Iterator[MemoryServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> MemoryServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "memory services are not bound; wrap dispatch in 'bind_services(...)' or pass explicit services"
        )
    return services


def resolve_services(explicit: MemoryServices | None) -> MemoryServices:
    return explicit if explicit is not None else current_services()


class MemoryContainer:
    def __init__(self, services: MemoryServices) -> None:
        self.services = services
        self.memory = MemoryService(
            scope_factory=services.scope_factory,
            write_policy=services.write_policy,
            retention_policy=services.retention_policy,
        )


def container_for(services: MemoryServices | None = None) -> MemoryContainer:
    return MemoryContainer(resolve_services(services))
