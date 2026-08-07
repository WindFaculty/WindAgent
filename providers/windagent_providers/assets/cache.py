"""
Idempotency cache for the Universal Asset Gateway (VP3D Phase 5).

The cache key is the CANONICAL requirement content + adapter id + adapter
version (see ``AssetRequirement.cache_key``). The same requirement resolved by
the same adapter version is looked up HERE before any network or generation
call happens (backlog item 3). The cache never stores credentials — only the
redacted resolution result.
"""

from __future__ import annotations

from typing import Dict, Optional

from windagent_core.domain.video_production.asset_resolution import (
    AssetResolutionResult,
)


class AssetResolutionCache:
    """Bounded in-memory idempotency cache (LRU eviction by access order)."""

    def __init__(self, *, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._entries: Dict[str, AssetResolutionResult] = {}
        self._access_order: Dict[str, int] = {}
        self._counter = 0

    def _touch(self, key: str) -> None:
        self._counter += 1
        self._access_order[key] = self._counter

    def get(self, key: str) -> Optional[AssetResolutionResult]:
        result = self._entries.get(key)
        if result is not None:
            self._touch(key)
        return result

    def put(self, key: str, result: AssetResolutionResult) -> None:
        if key in self._entries:
            self._entries[key] = result
            self._touch(key)
            return
        if len(self._entries) >= self._max_entries:
            oldest = min(self._access_order, key=self._access_order.get)
            self._entries.pop(oldest, None)
            self._access_order.pop(oldest, None)
        self._entries[key] = result
        self._touch(key)

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)
        self._access_order.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)


__all__ = ["AssetResolutionCache"]
