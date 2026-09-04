"""Module runtime: service composition and ambient scope."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry

from .events import AgentRuntimeEventFactory
from .ports import TransactionScope
from .services import AgentRuntimeService


@dataclass(frozen=True, slots=True)
class AgentRuntimeServices:
    scope_factory: Callable[[], TransactionScope]
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    event_factory: AgentRuntimeEventFactory = field(default_factory=AgentRuntimeEventFactory)


_SERVICES: ContextVar[AgentRuntimeServices | None] = ContextVar("agent_runtime_services", default=None)


@contextmanager
def bind_services(services: AgentRuntimeServices) -> Iterator[AgentRuntimeServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> AgentRuntimeServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError("agent runtime services are not bound; wrap the dispatch in 'bind_services(...)' or inject explicitly")
    return services


def resolve_services(explicit: AgentRuntimeServices | None) -> AgentRuntimeServices:
    return explicit if explicit is not None else current_services()


class AgentRuntimeContainer:
    def __init__(self, services: AgentRuntimeServices) -> None:
        self.services = services
        self.agent_runtime = AgentRuntimeService(
            scope_factory=services.scope_factory,
            clock=services.clock,
            event_factory=services.event_factory,
            telemetry=services.telemetry,
        )


def container_for(services: AgentRuntimeServices | None = None) -> AgentRuntimeContainer:
    return AgentRuntimeContainer(resolve_services(services))
