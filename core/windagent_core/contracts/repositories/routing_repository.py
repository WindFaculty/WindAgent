"""Routing repository ports for WindAgent Core (Phase 3 — Dependency Inversion).

These ports were formerly defined in ``windagent_providers.routing.ports``.
Core owns the ports; providers owns the adapters that implement them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class RouteLockRepositoryPort(Protocol):
    """Persistent store for route locks (one active lock per scope)."""

    def get_lock(self, scope_type: str, scope_id: str) -> Optional[Dict[str, Any]]: ...

    def get_lock_by_id(self, lock_id: str) -> Optional[Dict[str, Any]]: ...

    def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: Dict[str, Any],
        policy_version: int = 1,
    ) -> Dict[str, Any]: ...

    def release_lock(self, lock_id: str) -> bool: ...


@runtime_checkable
class RoutingAuditRepositoryPort(Protocol):
    """Durable audit trail for routing decisions (merge/split/reselect/failover)."""

    def record_event(
        self,
        action: str,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        lock_id: Optional[str] = None,
        canonical_model_id: Optional[str] = None,
        previous_canonical_model_id: Optional[str] = None,
        new_canonical_model_id: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        reason: Optional[str] = None,
        actor: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str: ...


@runtime_checkable
class EndpointBindingRepositoryPort(Protocol):
    """Persistent store for canonical models + endpoint bindings."""

    def register_discovery_snapshot(
        self, endpoint_id: str, discovered_models: List[Any]
    ) -> List[Dict[str, Any]]: ...

    def get_exact_equivalent_endpoints(
        self, canonical_model_id: str
    ) -> List[Dict[str, Any]]: ...

    def merge_canonical_models(
        self, source_canonical_id: str, target_canonical_id: str, actor: str = "system"
    ) -> bool: ...

    def split_binding(
        self, binding_id: str, new_canonical_name: str, actor: str = "system"
    ) -> Optional[Dict[str, Any]]: ...

    def get_audit_trails(self) -> List[Dict[str, Any]]: ...


@runtime_checkable
class CanonicalModelRepository(Protocol):
    """Persistent store for canonical model descriptors and metadata."""

    def get_canonical_model(self, canonical_model_id: str) -> Optional[Dict[str, Any]]: ...

    def list_canonical_models(self) -> List[Dict[str, Any]]: ...

    def save_canonical_model(self, model_data: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class RouteAttemptRepository(Protocol):
    """Persistent store for route execution attempts and failover tracking."""

    def record_attempt(
        self,
        lock_id: str,
        endpoint_id: Optional[str],
        provider_model_id: Optional[str],
        attempt_number: int,
        status: str,
        failure_category: Optional[str] = None,
        retry_after: Optional[float] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
    ) -> Dict[str, Any]: ...

    def get_attempts_for_lock(self, lock_id: str) -> List[Dict[str, Any]]: ...


@runtime_checkable
class RoutingUnitOfWork(Protocol):
    """Transactional Unit of Work scope for atomic routing operations."""

    def __enter__(self) -> "RoutingUnitOfWork": ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


# Spec name aliases for strict port compliance (kept for callers that used the
# provider-package aliases).
@runtime_checkable
class CanonicalModelRepositoryPort(CanonicalModelRepository, Protocol):
    """Alias for CanonicalModelRepository for port naming consistency."""


@runtime_checkable
class EndpointBindingRepository(EndpointBindingRepositoryPort, Protocol):
    """Alias for EndpointBindingRepositoryPort for backward compatibility."""


@runtime_checkable
class RouteLockRepository(RouteLockRepositoryPort, Protocol):
    """Alias for RouteLockRepositoryPort for backward compatibility."""


@runtime_checkable
class ProviderRoutingAuditRepository(RoutingAuditRepositoryPort, Protocol):
    """Alias for RoutingAuditRepositoryPort for backward compatibility."""


@runtime_checkable
class RouteAttemptRepositoryPort(RouteAttemptRepository, Protocol):
    """Alias for RouteAttemptRepository for port naming consistency."""


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