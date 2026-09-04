"""Module runtime: service composition and ambient scope (mirrors model_gateway)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from .events import StudioEventFactory
from .ports import TransactionScope
from .services import StudioService


@dataclass(frozen=True, slots=True)
class StudioServices:
    scope_factory: Callable[[], TransactionScope]
    secrets: SecretStore | None = None
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    event_factory: StudioEventFactory = field(default_factory=StudioEventFactory)


_SERVICES: ContextVar[StudioServices | None] = ContextVar("studio_services", default=None)


@contextmanager
def bind_services(services: StudioServices) -> Iterator[StudioServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> StudioServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "studio services are not bound; wrap the dispatch in 'bind_services(...)' or inject explicitly"
        )
    return services


def resolve_services(explicit: StudioServices | None) -> StudioServices:
    return explicit if explicit is not None else current_services()


class StudioContainer:
    def __init__(self, services: StudioServices) -> None:
        self.services = services
        self.studio = StudioService(
            scope_factory=services.scope_factory,
            clock=services.clock,
            event_factory=services.event_factory,
            telemetry=services.telemetry,
        )


def container_for(services: StudioServices | None = None) -> StudioContainer:
    return StudioContainer(resolve_services(services))
