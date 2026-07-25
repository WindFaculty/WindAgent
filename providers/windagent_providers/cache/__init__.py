"""
Provider cache and singleflight package for WindAgent Provider Subsystem V3.

Backends are swappable.  In-memory implementations are provided for development
and unit tests.  Production wiring should inject a distributed CachePort
adapter (Redis, etc.).
"""

from windagent_providers.cache.contracts import (
    CacheEntry,
    CacheNamespace,
    CacheTags,
    ResponseCacheKey,
    ResponseCacheHit,
    SingleFlightPort,
)
from windagent_core.contracts.providers.ports import CachePort
from windagent_providers.cache.backends import InMemoryCacheBackend
from windagent_providers.cache.eligibility import response_cache_eligible
from windagent_providers.cache.keys import build_response_cache_key
from windagent_providers.cache.cache_directive import to_provider_headers
from windagent_providers.cache.response_cache import ResponseCacheService
from windagent_providers.cache.discovery_cache import DiscoveryCacheService
from windagent_providers.cache.health_cache import HealthCacheService
from windagent_providers.cache.route_cache import RouteLockCacheService
from windagent_providers.cache.singleflight import InMemorySingleFlight

__all__ = [
    # Contracts
    "CacheEntry",
    "CacheNamespace",
    "CacheTags",
    "ResponseCacheKey",
    "ResponseCacheHit",
    "SingleFlightPort",
    "CachePort",
    # Backends
    "InMemoryCacheBackend",
    # Logic
    "response_cache_eligible",
    "build_response_cache_key",
    "to_provider_headers",
    # Services
    "ResponseCacheService",
    "DiscoveryCacheService",
    "HealthCacheService",
    "RouteLockCacheService",
    # Singleflight
    "InMemorySingleFlight",
]
