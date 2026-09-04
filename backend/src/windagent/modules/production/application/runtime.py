"""Module runtime: service composition and ambient scope (mirrors studio)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from .events import ProductionEventFactory
from .ports import TransactionScope
from .services import ProductionService


@dataclass(frozen=True, slots=True)
class ProductionServices:
    scope_factory: Callable[[], TransactionScope]
    secrets: SecretStore | None = None
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    event_factory: ProductionEventFactory = field(default_factory=ProductionEventFactory)


_SERVICES: ContextVar[ProductionServices | None] = ContextVar("production_services", default=None)


@contextmanager
def bind_services(services: ProductionServices) -> Iterator[ProductionServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> ProductionServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError("production services are not bound; wrap the dispatch in 'bind_services(...)' or inject explicitly")
    return services


def resolve_services(explicit: ProductionServices | None) -> ProductionServices:
    return explicit if explicit is not None else current_services()


class ProductionContainer:
    def __init__(self, services: ProductionServices) -> None:
        self.services = services
        self.production = ProductionService(
            scope_factory=services.scope_factory,
            clock=services.clock,
            event_factory=services.event_factory,
            telemetry=services.telemetry,
        )


def container_for(services: ProductionServices | None = None) -> ProductionContainer:
    return ProductionContainer(resolve_services(services))
