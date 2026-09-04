"""Module runtime: service composition and the ambient services scope.

Feature modules must be discoverable without constructor arguments
(``PackageModuleDiscovery``), so manifest handlers resolve collaborators
lazily.  HTTP routes and worker jobs bind a :class:`ModelGatewayServices`
instance into the ambient scope; handlers read it at ``handle`` time, or use
explicitly injected services in tests and embedded compositions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from windagent.kernel.time import Clock, SystemClock
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from ..providers.resolver import DefaultAdapterFactory
from .coordinator import EndpointExecutionCoordinator
from .gateway import ModelGateway
from .ports import AdapterFactory, TransactionScope
from .registry import ProviderRegistryService
from .route_locks import RouteLockService
from .selector import EndpointSelector


@dataclass(frozen=True, slots=True)
class ModelGatewayServices:
    """The collaborators every model-gateway handler needs."""

    scope_factory: Callable[[], TransactionScope]
    secrets: SecretStore
    clock: Clock = field(default_factory=SystemClock)
    telemetry: Telemetry | None = None
    adapter_factory: AdapterFactory = field(default_factory=DefaultAdapterFactory)


_SERVICES: ContextVar[ModelGatewayServices | None] = ContextVar(
    "model_gateway_services", default=None
)


@contextmanager
def bind_services(services: ModelGatewayServices) -> Iterator[ModelGatewayServices]:
    """Bind the module services for the duration of one dispatch."""
    token = _SERVICES.set(services)
    try:
        yield services
    finally:
        _SERVICES.reset(token)


def current_services() -> ModelGatewayServices:
    """Return the ambient services; fail fast when nothing is bound."""
    services = _SERVICES.get()
    if services is None:
        raise RuntimeError(
            "model gateway services are not bound; wrap the dispatch in "
            "'bind_services(...)' or inject services explicitly"
        )
    return services


def resolve_services(explicit: ModelGatewayServices | None) -> ModelGatewayServices:
    """Prefer explicitly injected services over the ambient scope."""
    return explicit if explicit is not None else current_services()


class ModelGatewayContainer:
    """The composed application services for one services instance."""

    def __init__(self, services: ModelGatewayServices) -> None:
        self.services = services
        self.registry = ProviderRegistryService(
            scope_factory=services.scope_factory,
            secrets=services.secrets,
            clock=services.clock,
        )
        self.locks = RouteLockService(
            scope_factory=services.scope_factory,
            clock=services.clock,
        )
        self.selector = EndpointSelector()
        self.coordinator = EndpointExecutionCoordinator(
            scope_factory=services.scope_factory,
            secrets=services.secrets,
            adapter_factory=services.adapter_factory,
            selector=self.selector,
            clock=services.clock,
            telemetry=services.telemetry,
        )
        self.gateway = ModelGateway(
            scope_factory=services.scope_factory,
            locks=self.locks,
            selector=self.selector,
            coordinator=self.coordinator,
            clock=services.clock,
            telemetry=services.telemetry,
        )


def container_for(services: ModelGatewayServices | None = None) -> ModelGatewayContainer:
    """Compose the container from explicit or ambient services."""
    return ModelGatewayContainer(resolve_services(services))
