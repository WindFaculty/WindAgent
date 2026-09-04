"""Module runtime composition for Live Record."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from .events import LiveRecordEventFactory
from .ports import TransactionScope
from .services import LiveRecordService


@dataclass(frozen=True, slots=True)
class LiveRecordServices:
    scope_factory: Callable[[], TransactionScope]
    secrets: SecretStore | None = None
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    event_factory: LiveRecordEventFactory = field(default_factory=LiveRecordEventFactory)


_SERVICES: ContextVar[LiveRecordServices | None] = ContextVar("live_record_services", default=None)


@contextmanager
def bind_services(services: LiveRecordServices) -> Iterator[LiveRecordServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> LiveRecordServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError("live_record services are not bound; wrap dispatch in 'bind_services(...)' or inject explicitly")
    return services


def resolve_services(explicit: LiveRecordServices | None) -> LiveRecordServices:
    return explicit if explicit is not None else current_services()


class LiveRecordContainer:
    def __init__(self, services: LiveRecordServices) -> None:
        self.services = services
        self.live_record = LiveRecordService(scope_factory=services.scope_factory, clock=services.clock, event_factory=services.event_factory, telemetry=services.telemetry)


def container_for(services: LiveRecordServices | None = None) -> LiveRecordContainer:
    return LiveRecordContainer(resolve_services(services))
