"""Canonical Provider Port Protocols for WindAgent Core contracts (Phase 5).

Pure-Python ports with zero framework dependencies. Provider adapters and the
routing subsystem implement these; Core only defines them.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.contracts.providers.capabilities import (
    ModelDescriptor,
    QuotaState,
)
from windagent_core.contracts.providers.model_capabilities import (
    ModelCapabilityProfile,
)


@runtime_checkable
class EndpointRegistryPort(Protocol):
    """Port for querying and updating provider endpoint configurations."""

    async def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def list_endpoints_for_canonical_model(
        self, canonical_model_id: str
    ) -> List[Dict[str, Any]]:
        ...


@runtime_checkable
class CanonicalModelRegistryPort(Protocol):
    """Port for querying canonical model catalog and capabilities."""

    async def get_canonical_model(
        self, canonical_model_id: str
    ) -> Optional[ModelDescriptor]:
        ...

    async def list_canonical_models(self) -> List[ModelDescriptor]:
        ...


@runtime_checkable
class RouteLockPort(Protocol):
    """Port for creating, reading, and releasing scope-based persistent route locks."""

    async def get_lock(
        self, scope_type: str, scope_id: str
    ) -> Optional[Dict[str, Any]]:
        ...

    async def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...

    async def release_lock(self, lock_id: str) -> bool:
        ...


@runtime_checkable
class RouteAttemptPort(Protocol):
    """Port for recording individual provider execution attempts."""

    async def record_attempt(
        self,
        route_lock_id: str,
        turn_id: Optional[str],
        attempt_index: int,
        provider_binding_id: Optional[str],
        status: str,
        http_status: Optional[int] = None,
        error_class: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        endpoint_id: Optional[str] = None,
    ) -> str:
        ...


@runtime_checkable
class QuotaStatePort(Protocol):
    """Port for querying and updating provider quota snapshots."""

    async def get_quota_state(self, provider_id: str) -> Optional[QuotaState]:
        ...

    async def update_quota_state(self, provider_id: str, snapshot: QuotaState) -> None:
        ...


@runtime_checkable
class EndpointStatePort(Protocol):
    """Port for managing endpoint health, circuit breaker state, and 429 cooldowns."""

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        ...

    async def record_failure(
        self, endpoint_id: str, error_class: str, status_code: Optional[int]
    ) -> None:
        ...

    async def set_cooldown(self, endpoint_id: str, cooldown_until: datetime) -> None:
        ...

    async def is_available(self, endpoint_id: str) -> bool:
        ...


@runtime_checkable
class CachePort(Protocol):
    """Port for route caching, discovery caching, and response caching."""

    async def get(self, key: str) -> Optional[Any]:
        ...

    async def set(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        ...

    async def delete(self, key: str) -> bool:
        ...


@runtime_checkable
class UsageLedgerPort(Protocol):
    """Port for recording token usage, latencies, and estimated cost logs."""

    async def log_usage(
        self,
        canonical_model_id: str,
        provider_model_id: str,
        endpoint_id: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        cost_usd: float,
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# Roadmap provider ports (Phase 3 — Dependency Inversion).
#
# These are the neutral provider execution/health/discovery/registry/audit
# contracts the intelligence model-router policy depends on. Provider adapters
# satisfy them structurally; Core only defines them.
# ---------------------------------------------------------------------------


@runtime_checkable
class ProviderHealthPort(Protocol):
    """Port for querying a provider's health and quota state."""

    @property
    def provider_name(self) -> str:
        """Read-only provider identity used by the model-router policy."""
        ...

    async def health(self) -> Any:
        """Return a health record exposing ``.healthy``."""

    async def get_quota(self) -> Any:
        """Return a quota snapshot exposing ``.has_quota``."""


@runtime_checkable
class ModelExecutionPort(Protocol):
    """Port for executing a model generation call."""

    async def generate(self, request: Any) -> Any:
        ...

    def estimate_cost(self, request: Any) -> float:
        ...


@runtime_checkable
class ModelRegistryPort(Protocol):
    """Port for discovering available models and their capability profiles."""

    async def list_models(self) -> List[str]:
        ...

    def capabilities(self) -> List[ModelCapabilityProfile]:
        ...


@runtime_checkable
class ProviderDiscoveryPort(Protocol):
    """Port for discovering provider models and capability profiles."""

    async def discover(self, provider_id: str) -> List[ModelCapabilityProfile]:
        ...


@runtime_checkable
class RoutingAuditPort(Protocol):
    """Port for recording routing decisions for auditability."""

    async def record_route(
        self,
        *,
        session_id: str,
        task_id: str,
        canonical_model_id: str,
        provider_name: str,
        reasons: List[str],
        fallback_chain: List[str],
    ) -> None:
        ...


__all__ = [
    "EndpointRegistryPort",
    "CanonicalModelRegistryPort",
    "RouteLockPort",
    "RouteAttemptPort",
    "QuotaStatePort",
    "EndpointStatePort",
    "CachePort",
    "UsageLedgerPort",
    "ProviderHealthPort",
    "ModelExecutionPort",
    "ModelRegistryPort",
    "ProviderDiscoveryPort",
    "RoutingAuditPort",
]
