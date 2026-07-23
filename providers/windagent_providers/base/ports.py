"""
Abstract Port Interfaces for WindAgent Provider Routing Subsystem V3.
Decouples core transport logic from persistence, ORM, frameworks, and storage drivers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import (
    CacheDirective, ConnectionTestResult, DiscoveredModel, ModelDescriptor,
    ProviderHealth, QuotaState, RateLimitState
)


class EndpointRegistryPort(ABC):
    """Port for querying and updating provider endpoint configurations."""

    @abstractmethod
    async def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves provider endpoint binding details by ID."""
        pass

    @abstractmethod
    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> List[Dict[str, Any]]:
        """Lists active endpoint bindings matching exact canonical model ID."""
        pass


class CanonicalModelRegistryPort(ABC):
    """Port for querying canonical model catalog and capabilities."""

    @abstractmethod
    async def get_canonical_model(self, canonical_model_id: str) -> Optional[ModelDescriptor]:
        """Retrieves canonical model descriptor."""
        pass

    @abstractmethod
    async def list_canonical_models(self) -> List[ModelDescriptor]:
        """Lists registered canonical models."""
        pass


class RouteLockPort(ABC):
    """Port for creating, reading, and releasing scope-based persistent route locks."""

    @abstractmethod
    async def get_lock(self, scope_type: str, scope_id: str) -> Optional[Dict[str, Any]]:
        """Reads active route lock for the scope (session/task/workflow)."""
        pass

    @abstractmethod
    async def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persists a new immutable route lock for the scope."""
        pass

    @abstractmethod
    async def release_lock(self, lock_id: str) -> bool:
        """Releases or inactivates a route lock."""
        pass


class RouteAttemptPort(ABC):
    """Port for recording individual provider execution attempts."""

    @abstractmethod
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
    ) -> str:
        """Persists a route attempt record and returns attempt ID."""
        pass


class QuotaStatePort(ABC):
    """Port for querying and updating provider quota snapshots."""

    @abstractmethod
    async def get_quota_state(self, provider_id: str) -> Optional[QuotaState]:
        """Queries remaining quota state for provider."""
        pass

    @abstractmethod
    async def update_quota_state(self, provider_id: str, snapshot: QuotaState) -> None:
        """Updates provider quota snapshot."""
        pass


class EndpointStatePort(ABC):
    """Port for managing endpoint health, circuit breaker state, and 429 cooldowns."""

    @abstractmethod
    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        """Records successful invocation metrics."""
        pass

    @abstractmethod
    async def record_failure(self, endpoint_id: str, error_class: str, status_code: Optional[int]) -> None:
        """Records invocation failure for health scoring and circuit breaker."""
        pass

    @abstractmethod
    async def set_cooldown(self, endpoint_id: str, cooldown_until: datetime) -> None:
        """Applies cooldown timer (e.g. on HTTP 429 rate limit)."""
        pass

    @abstractmethod
    async def is_available(self, endpoint_id: str) -> bool:
        """Returns True if endpoint is healthy and not in cooldown/open circuit."""
        pass


class CachePort(ABC):
    """Port for route caching, discovery caching, and response caching."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieves cached value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores value in cache with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Deletes cached key."""
        pass


class UsageLedgerPort(ABC):
    """Port for recording token usage, latencies, and estimated cost logs."""

    @abstractmethod
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
        """Logs execution usage record."""
        pass
