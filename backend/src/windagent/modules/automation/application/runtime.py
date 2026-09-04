"""Module runtime: service composition and ambient scope (mirrors studio/model_gateway)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from .events import AutomationEventFactory
from .executor import ToolExecutor
from .ports import TransactionScope
from .registry import RuntimeRegistry, ToolRegistry
from .services import AutomationService


@dataclass(frozen=True, slots=True)
class AutomationServices:
    scope_factory: Callable[[], TransactionScope]
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)
    runtime_registry: RuntimeRegistry = field(default_factory=RuntimeRegistry)
    secrets: SecretStore | None = None
    policy_engine: object | None = None
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    event_factory: AutomationEventFactory = field(default_factory=AutomationEventFactory)


_SERVICES: ContextVar[AutomationServices | None] = ContextVar("automation_services", default=None)


@contextmanager
def bind_services(services: AutomationServices) -> Iterator[AutomationServices]:
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> AutomationServices:
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "automation services are not bound; wrap the dispatch in 'bind_services(...)' or inject explicitly"
        )
    return services


def resolve_services(explicit: AutomationServices | None) -> AutomationServices:
    return explicit if explicit is not None else current_services()


class AutomationContainer:
    def __init__(self, services: AutomationServices) -> None:
        self.services = services
        executor = ToolExecutor(
            tool_registry=services.tool_registry,
            runtime_registry=services.runtime_registry,
            policy_engine=services.policy_engine,
        )
        self.automation = AutomationService(
            scope_factory=services.scope_factory,
            tool_registry=services.tool_registry,
            runtime_registry=services.runtime_registry,
            executor=executor,
            clock=services.clock,
            event_factory=services.event_factory,
            telemetry=services.telemetry,
        )


def container_for(services: AutomationServices | None = None) -> AutomationContainer:
    return AutomationContainer(resolve_services(services))
