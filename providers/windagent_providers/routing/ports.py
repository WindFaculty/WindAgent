"""
Synchronous routing repository ports for Phase 1.

Since Phase 3 the ports live in core. Application services (CanonicalModelRegistryService,
RouteLockService) depend ONLY on these ports. Concrete SQL implementations live in
``windagent_storage`` and receive a synchronous SQLAlchemy ``Session``. In-memory fakes
live under ``tests/fakes``.

This module re-exports the canonical ports from core for callers that imported
them from the provider package.
"""

from windagent_core.contracts.repositories.routing_repository import (
    CanonicalModelRepository,
    CanonicalModelRepositoryPort,
    EndpointBindingRepository,
    EndpointBindingRepositoryPort,
    ProviderRoutingAuditRepository,
    RouteAttemptRepository,
    RouteAttemptRepositoryPort,
    RouteLockRepository,
    RouteLockRepositoryPort,
    RoutingAuditRepositoryPort,
    RoutingUnitOfWork,
)

__all__ = [
    "RouteLockRepositoryPort",
    "RoutingAuditRepositoryPort",
    "EndpointBindingRepositoryPort",
    "CanonicalModelRepository",
    "RouteAttemptRepository",
    "RoutingUnitOfWork",
    "CanonicalModelRepositoryPort",
    "EndpointBindingRepository",
    "RouteLockRepository",
    "ProviderRoutingAuditRepository",
    "RouteAttemptRepositoryPort",
]