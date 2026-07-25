"""
Route lock cache service for WindAgent Provider Subsystem V3.

Key:
    route-lock:{scope_type}:{scope_id}

Database is source of truth.  This cache is read-through and invalidated on
write so a stale lock cannot survive after reselection.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.providers.ports import CachePort


ROUTE_LOCK_TTL_SECONDS = 60


class RouteLockCacheService:
    """Read-through cache for route locks.  Always falls back to persistent port."""

    def __init__(
        self,
        cache: CachePort,
        persistent_port: Any,
        ttl_seconds: int = ROUTE_LOCK_TTL_SECONDS,
    ):
        self._cache = cache
        self._persistent = persistent_port
        self._ttl_seconds = ttl_seconds

    def _key(self, scope_type: str, scope_id: str) -> str:
        return f"route-lock:{scope_type}:{scope_id}"

    async def get_lock(
        self, scope_type: str, scope_id: str
    ) -> Optional[Dict[str, Any]]:
        key = self._key(scope_type, scope_id)

        try:
            cached = await self._cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            pass

        persisted = await self._persistent.get(scope_type, scope_id)
        if persisted is not None:
            try:
                await self._cache.set(key, persisted, ttl_seconds=self._ttl_seconds)
            except Exception:
                pass
        return persisted

    async def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        record = await self._persistent.create(scope_type, scope_id, *args, **kwargs)
        key = self._key(scope_type, scope_id)
        try:
            await self._cache.set(key, record, ttl_seconds=self._ttl_seconds)
        except Exception:
            pass
        return record

    async def release_lock(self, scope_type: str, scope_id: str) -> bool:
        key = self._key(scope_type, scope_id)
        try:
            await self._cache.delete(key)
        except Exception:
            pass
        return True
