"""
Endpoint state cache service for WindAgent Provider Subsystem V3.

Keys:
    endpoint-health:{endpoint_id}
    endpoint-cooldown:{endpoint_id}
    endpoint-circuit:{endpoint_id}
    endpoint-quota:{endpoint_id}

Short TTL because these values change quickly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_providers.base.contracts import ProviderHealth, QuotaState
from windagent_providers.base.ports import CachePort


HEALTH_TTL_SECONDS = 15
COOLDOWN_TTL_SECONDS = 60
CIRCUIT_TTL_SECONDS = 60
QUOTA_TTL_SECONDS = 30


class HealthCacheService:
    """Read-through cache for endpoint health/quota/circuit/cooldown."""

    def __init__(self, cache: CachePort):
        self._cache = cache

    async def get_health(self, endpoint_id: str) -> Optional[ProviderHealth]:
        return await self._get_typed(f"endpoint-health:{endpoint_id}", ProviderHealth)

    async def set_health(self, endpoint_id: str, health: ProviderHealth) -> None:
        await self._set(f"endpoint-health:{endpoint_id}", health, HEALTH_TTL_SECONDS)

    async def get_cooldown(self, endpoint_id: str) -> Optional[datetime]:
        value = await self._get(f"endpoint-cooldown:{endpoint_id}")
        if isinstance(value, datetime):
            return value
        return None

    async def set_cooldown(self, endpoint_id: str, until: datetime) -> None:
        await self._set(f"endpoint-cooldown:{endpoint_id}", until, COOLDOWN_TTL_SECONDS)

    async def get_circuit(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        return await self._get(f"endpoint-circuit:{endpoint_id}")

    async def set_circuit(self, endpoint_id: str, state: Dict[str, Any]) -> None:
        await self._set(f"endpoint-circuit:{endpoint_id}", state, CIRCUIT_TTL_SECONDS)

    async def get_quota(self, endpoint_id: str) -> Optional[QuotaState]:
        return await self._get_typed(f"endpoint-quota:{endpoint_id}", QuotaState)

    async def set_quota(self, endpoint_id: str, quota: QuotaState) -> None:
        await self._set(f"endpoint-quota:{endpoint_id}", quota, QUOTA_TTL_SECONDS)

    async def _get(self, key: str) -> Any:
        try:
            return await self._cache.get(key)
        except Exception:
            return None

    async def _get_typed(self, key: str, cls: type) -> Any:
        value = await self._get(key)
        if isinstance(value, cls):
            return value
        return None

    async def _set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self._cache.set(key, value, ttl_seconds=ttl)
        except Exception:
            pass
