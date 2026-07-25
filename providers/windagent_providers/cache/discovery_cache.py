"""
Discovery cache service for WindAgent Provider Subsystem V3.

Key:
    models:{endpoint_id}:{credential_version}:{protocol_version}

Invalidated on credential rotation or protocol bump.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_providers.base.contracts import DiscoveredModel
from windagent_core.contracts.providers.ports import CachePort


DISCOVERY_TTL_SECONDS = 300


class DiscoveryCacheService:
    """Thin read-through cache around endpoint model discovery."""

    def __init__(self, cache: CachePort, ttl_seconds: int = DISCOVERY_TTL_SECONDS):
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def _key(
        self,
        endpoint_id: str,
        credential_version: str,
        protocol_version: str,
    ) -> str:
        return f"models:{endpoint_id}:{credential_version}:{protocol_version}"

    async def get(
        self,
        endpoint_id: str,
        credential_version: str,
        protocol_version: str,
    ) -> Optional[List[DiscoveredModel]]:
        key = self._key(endpoint_id, credential_version, protocol_version)
        try:
            value = await self._cache.get(key)
        except Exception:
            return None
        if isinstance(value, list):
            return value
        return None

    async def set(
        self,
        endpoint_id: str,
        credential_version: str,
        protocol_version: str,
        models: List[DiscoveredModel],
    ) -> None:
        key = self._key(endpoint_id, credential_version, protocol_version)
        try:
            await self._cache.set(key, models, ttl_seconds=self._ttl_seconds)
        except Exception:
            pass

    async def invalidate_endpoint(self, endpoint_id: str) -> int:
        """Invalidate all discovery entries for an endpoint."""
        if not hasattr(self._cache, "invalidate_tag"):
            return 0
        try:
            return await self._cache.invalidate_tag(f"endpoint:{endpoint_id}")
        except Exception:
            return 0

    async def invalidate_credential_rotation(
        self,
        endpoint_id: str,
        old_credential_version: str,
        protocol_version: str,
    ) -> bool:
        """Invalidate discovery cache after credential rotation."""
        key = self._key(endpoint_id, old_credential_version, protocol_version)
        try:
            return await self._cache.delete(key)
        except Exception:
            return False
