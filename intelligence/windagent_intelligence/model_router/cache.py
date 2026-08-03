"""
Router Cache for WindAgent Intelligence (Phase 22).
Provides cache key generation that includes model, provider compatibility, prompt hash,
and tool schema hash. Supports endpoint failover that keeps the same canonical model
while switching to a different provider endpoint (e.g., on 429 or transient errors).
"""

from __future__ import annotations
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger("windagent.intelligence.model_router.cache")


@dataclass(frozen=True)
class RouterCacheKey:
    """Cache key for router decisions. Includes all factors that affect routing."""
    canonical_model: str
    provider_name: str
    prompt_hash: str
    tool_schema_hash: str

    def to_cache_key(self) -> str:
        """Generates a deterministic cache key string."""
        raw = json.dumps({
            "model": self.canonical_model,
            "provider": self.provider_name,
            "prompt_hash": self.prompt_hash,
            "tool_schema_hash": self.tool_schema_hash,
        }, sort_keys=True)
        return f"route_cache_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


@dataclass
class CachedRouteEntry:
    """A cached route decision with expiration."""
    cache_key: str
    canonical_model: str
    provider_name: str
    endpoint_id: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # 0 = no expiration
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at


@dataclass
class EndpointFailoverConfig:
    """Configuration for endpoint failover behavior."""
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    # Whether to allow endpoint failover (changing provider endpoint while keeping same model)
    allow_endpoint_failover: bool = True
    # Set of endpoint IDs that are currently blacklisted due to errors
    blacklisted_endpoints: set = field(default_factory=set)


class RouterCache:
    """Cache for model routing decisions with failover support.
    On 429 or endpoint error: switches to equivalent endpoint but keeps the same canonical model.
    Never silently changes the model.
    """

    def __init__(self, default_ttl_seconds: float = 300.0):
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: Dict[str, CachedRouteEntry] = {}
        self._endpoint_health: Dict[str, float] = {}  # endpoint_id -> next_retry_at timestamp
        self._endpoint_models: Dict[str, List[str]] = {}  # endpoint_id -> [canonical_model_ids]
        self.failover_config = EndpointFailoverConfig()

    # ------------------------------------------------------------------
    # Cache key generation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_prompt_hash(prompt: str) -> str:
        """Computes a deterministic prompt hash."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def compute_tool_schema_hash(tool_definitions: List[Dict[str, Any]]) -> str:
        """Computes a hash of tool schemas for cache key."""
        raw = json.dumps(tool_definitions, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def build_cache_key(
        self,
        canonical_model: str,
        provider_name: str,
        prompt: str,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
    ) -> RouterCacheKey:
        """Builds a full cache key from routing factors."""
        prompt_hash = self.compute_prompt_hash(prompt)
        tool_hash = self.compute_tool_schema_hash(tool_schemas or [])
        return RouterCacheKey(
            canonical_model=canonical_model,
            provider_name=provider_name,
            prompt_hash=prompt_hash,
            tool_schema_hash=tool_hash,
        )

    # ------------------------------------------------------------------
    # Cache operations
    # ------------------------------------------------------------------

    def get(self, cache_key: RouterCacheKey) -> Optional[CachedRouteEntry]:
        """Retrieves a cached route entry if not expired."""
        key_str = cache_key.to_cache_key()
        entry = self._cache.get(key_str)

        if entry is None:
            return None

        if entry.is_expired:
            del self._cache[key_str]
            return None

        entry.hit_count += 1
        return entry

    def set(
        self,
        cache_key: RouterCacheKey,
        provider_name: str,
        endpoint_id: str,
        ttl_seconds: Optional[float] = None,
    ) -> CachedRouteEntry:
        """Caches a route decision."""
        key_str = cache_key.to_cache_key()
        now = time.time()
        ttl = ttl_seconds or self.default_ttl_seconds

        entry = CachedRouteEntry(
            cache_key=key_str,
            canonical_model=cache_key.canonical_model,
            provider_name=provider_name,
            endpoint_id=endpoint_id,
            created_at=now,
            expires_at=now + ttl,
        )
        self._cache[key_str] = entry
        return entry

    def invalidate(self, cache_key: RouterCacheKey) -> bool:
        """Invalidates a cache entry."""
        key_str = cache_key.to_cache_key()
        if key_str in self._cache:
            del self._cache[key_str]
            return True
        return False

    def clear(self) -> int:
        """Clears all cached routes. Returns count cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    # ------------------------------------------------------------------
    # Endpoint failover (keep same model, change endpoint)
    # ------------------------------------------------------------------

    def register_endpoint(self, endpoint_id: str, supported_models: List[str]) -> None:
        """Registers an endpoint and the canonical models it supports."""
        self._endpoint_models[endpoint_id] = supported_models

    def report_endpoint_error(self, endpoint_id: str, status_code: int) -> None:
        """Reports an endpoint error. On 429 or 5xx, blacklists temporarily.
        Does NOT change the canonical model — only changes the endpoint.
        """
        if not self.failover_config.allow_endpoint_failover:
            return

        if status_code in (429, 500, 502, 503, 504):
            delay = self.failover_config.base_delay_seconds
            # Exponential backoff based on consecutive failures
            self.failover_config.blacklisted_endpoints.add(endpoint_id)
            self._endpoint_health[endpoint_id] = time.time() + delay
            logger.warning(
                f"Endpoint [{endpoint_id}] reported error {status_code}. "
                f"Blacklisted until retry_at. Keeping canonical model unchanged."
            )

    def find_failover_endpoint(self, canonical_model: str, current_endpoint: Optional[str] = None) -> Optional[str]:
        """Finds an alternative endpoint for the same canonical model.
        Returns None if no failover endpoint is available.
        """
        candidates = []
        for endpoint_id, models in self._endpoint_models.items():
            if canonical_model not in models:
                continue
            if endpoint_id == current_endpoint:
                continue
            if endpoint_id in self.failover_config.blacklisted_endpoints:
                # Check if blacklist has expired
                retry_at = self._endpoint_health.get(endpoint_id, 0)
                if time.time() < retry_at:
                    continue
                # Blacklist expired, remove it
                self.failover_config.blacklisted_endpoints.discard(endpoint_id)
            candidates.append(endpoint_id)

        if candidates:
            logger.info(f"Failover endpoint found for model [{canonical_model}]: {candidates[0]}")
            return candidates[0]

        logger.warning(f"No failover endpoint available for model [{canonical_model}]")
        return None

    def reset_endpoint_health(self, endpoint_id: str) -> None:
        """Resets the health status of an endpoint."""
        self.failover_config.blacklisted_endpoints.discard(endpoint_id)
        self._endpoint_health.pop(endpoint_id, None)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "cache_entries": len(self._cache),
            "registered_endpoints": len(self._endpoint_models),
            "blacklisted_endpoints": len(self.failover_config.blacklisted_endpoints),
            "default_ttl_seconds": self.default_ttl_seconds,
        }
