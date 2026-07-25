"""
Response cache service for WindAgent Provider Subsystem V3.

Thin layer over CachePort with key building, eligibility checks, and
provider-behavior-version tagging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from windagent_providers.base.contracts import ProviderRequest, ProviderResponse
from windagent_core.contracts.providers.ports import CachePort
from windagent_providers.cache.contracts import CacheEntry, CacheNamespace, CacheTags
from windagent_providers.cache.eligibility import response_cache_eligible
from windagent_providers.cache.keys import build_response_cache_key


@dataclass
class ResponseCacheResult:
    hit: bool
    response: Optional[ProviderResponse] = None
    cache_key: Optional[str] = None


DEFAULT_RESPONSE_TTL_SECONDS = 300


class ResponseCacheService:
    """Safe response cache.  Misses are transparent; failures are swallowed."""

    def __init__(
        self,
        cache: CachePort,
        provider_behavior_version: str = "1",
        default_ttl_seconds: int = DEFAULT_RESPONSE_TTL_SECONDS,
        equivalence_level: str = "exact_revision",
    ):
        self._cache = cache
        self._provider_behavior_version = provider_behavior_version
        self._default_ttl_seconds = default_ttl_seconds
        self._equivalence_level = equivalence_level

    async def get(
        self,
        request: ProviderRequest,
        namespace: CacheNamespace,
        canonical_model_id: str,
        *,
        revision: Optional[str] = None,
        explicit_opt_in: bool = False,
    ) -> ResponseCacheResult:
        if not response_cache_eligible(
            request,
            equivalence_level=self._equivalence_level,
            explicit_opt_in=explicit_opt_in,
        ):
            return ResponseCacheResult(hit=False)

        key_obj = build_response_cache_key(
            request,
            namespace,
            canonical_model_id,
            revision=revision,
            provider_behavior_version=self._provider_behavior_version,
        )
        key = key_obj.to_string()

        try:
            entry = await self._cache.get(key)
        except Exception:
            # Cache backend unavailable must not break execution.
            return ResponseCacheResult(hit=False, cache_key=key)

        if entry is None:
            return ResponseCacheResult(hit=False, cache_key=key)

        if isinstance(entry, CacheEntry):
            value = entry.value
        else:
            value = entry

        if not isinstance(value, ProviderResponse):
            return ResponseCacheResult(hit=False, cache_key=key)

        # ponytail: trust stored canonical model was normalized at write time.
        value.canonical_model_id = canonical_model_id
        return ResponseCacheResult(
            hit=True,
            response=value,
            cache_key=key,
        )

    async def set(
        self,
        request: ProviderRequest,
        namespace: CacheNamespace,
        canonical_model_id: str,
        response: ProviderResponse,
        *,
        revision: Optional[str] = None,
        explicit_opt_in: bool = False,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        if not response_cache_eligible(
            request,
            equivalence_level=self._equivalence_level,
            explicit_opt_in=explicit_opt_in,
        ):
            return False

        key_obj = build_response_cache_key(
            request,
            namespace,
            canonical_model_id,
            revision=revision,
            provider_behavior_version=self._provider_behavior_version,
        )
        key = key_obj.to_string()

        entry = CacheEntry(
            value=response,
            tags=CacheTags(
                canonical_model_id=canonical_model_id,
                revision=revision,
                provider_behavior_version=self._provider_behavior_version,
            ),
            ttl_seconds=ttl_seconds or self._default_ttl_seconds,
        )

        try:
            await self._cache.set(
                key, entry, ttl_seconds=ttl_seconds or self._default_ttl_seconds
            )
            return True
        except Exception:
            return False

    async def invalidate_model(self, canonical_model_id: str) -> int:
        """Invalidate all cached responses for a canonical model."""
        if hasattr(self._cache, "invalidate_tag"):
            try:
                return await self._cache.invalidate_tag(f"cm:{canonical_model_id}")
            except Exception:
                pass
        return 0
