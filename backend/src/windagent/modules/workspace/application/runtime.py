"""Module runtime: service composition and ambient scope for Workspace."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .ports import TransactionScope
from .services import WorkspaceService


@dataclass(frozen=True, slots=True)
class WorkspaceServices:
    transaction_factory: Callable[[], TransactionScope]


_SERVICES: ContextVar[WorkspaceServices | None] = ContextVar("workspace_services", default=None)


@contextmanager
def bind_services(services: WorkspaceServices) -> Iterator[WorkspaceServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> WorkspaceServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "workspace services are not bound; wrap dispatch in 'bind_services(...)' or pass explicit services"
        )
    return services


def resolve_services(explicit: WorkspaceServices | None) -> WorkspaceServices:
    return explicit if explicit is not None else current_services()


class WorkspaceContainer:
    def __init__(self, services: WorkspaceServices) -> None:
        self.services = services
        self.workspace = WorkspaceService(transaction_factory=services.transaction_factory)


def container_for(services: WorkspaceServices | None = None) -> WorkspaceContainer:
    return WorkspaceContainer(resolve_services(services))
