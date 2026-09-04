"""Module runtime: service composition and ambient scope for Quality."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .ports import TransactionScope
from .services import QualityService


@dataclass(frozen=True, slots=True)
class QualityServices:
    transaction_factory: Callable[[], TransactionScope]


_SERVICES: ContextVar[QualityServices | None] = ContextVar("quality_services", default=None)


@contextmanager
def bind_services(services: QualityServices) -> Iterator[QualityServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> QualityServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "quality services are not bound; wrap dispatch in 'bind_services(...)' or pass explicit services"
        )
    return services


def resolve_services(explicit: QualityServices | None) -> QualityServices:
    return explicit if explicit is not None else current_services()


class QualityContainer:
    def __init__(self, services: QualityServices) -> None:
        self.services = services
        self.quality = QualityService(transaction_factory=services.transaction_factory)


def container_for(services: QualityServices | None = None) -> QualityContainer:
    return QualityContainer(resolve_services(services))
