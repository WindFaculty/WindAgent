"""Model-gateway application queries."""

from __future__ import annotations

from windagent.platform.queries import Query

from ..domain.route_lock import RouteLockRecord
from ..domain.rules import RuleMatchContext
from .gateway import RouteDecision
from .models import EndpointView, ModelView, ProviderView, ReceiptView, RuleView


class ListProviders(Query[tuple[ProviderView, ...]]):
    """List every registered provider (never secret material)."""

    __slots__ = ()


class GetProvider(Query[ProviderView]):
    """Fetch one provider view (raises when missing)."""

    __slots__ = ("provider_id",)

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id


class ListEndpoints(Query[tuple[EndpointView, ...]]):
    """List one provider's endpoints."""

    __slots__ = ("provider_id",)

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id


class ListCanonicalModels(Query[tuple[ModelView, ...]]):
    """List the canonical catalog with bindings."""

    __slots__ = ()


class ListRoutingRules(Query[tuple[RuleView, ...]]):
    """List every routing rule."""

    __slots__ = ()


class GetRouteLock(Query[RouteLockRecord]):
    """Fetch one route lock by id (raises when missing)."""

    __slots__ = ("lock_id",)

    def __init__(self, lock_id: str) -> None:
        self.lock_id = lock_id


class GetActiveRouteLock(Query[RouteLockRecord | None]):
    """Fetch the active lock for a scope, when one exists."""

    __slots__ = ("scope_type", "scope_id")

    def __init__(self, scope_type: str, scope_id: str) -> None:
        self.scope_type = scope_type
        self.scope_id = scope_id


class SimulateRoute(Query[RouteDecision]):
    """Dry-run a routing decision without creating a lock."""

    __slots__ = ("context",)

    def __init__(self, context: RuleMatchContext) -> None:
        self.context = context


class ListReceipts(Query[tuple[ReceiptView, ...]]):
    """List recent routing receipts, optionally scoped to one task."""

    __slots__ = ("task_id", "limit")

    def __init__(self, task_id: str | None = None, limit: int = 50) -> None:
        self.task_id = task_id
        self.limit = limit
