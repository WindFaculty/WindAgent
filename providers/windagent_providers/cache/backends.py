"""
In-memory CachePort backend for development and unit tests.

Ponytail adapter: production should inject a distributed cache backend.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from windagent_providers.base.ports import CachePort


class InMemoryCacheBackend(CachePort):
    """
    Thread-safe in-memory cache implementing CachePort.

    Supports TTL, tag-based invalidation, and graceful degradation.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._tag_index: Dict[str, set] = {}
        self._mutex = threading.RLock()

    async def get(self, key: str) -> Optional[Any]:
        with self._mutex:
            record = self._data.get(key)
            if record is None:
                return None
            if record["expires_at"] is not None and time.time() > record["expires_at"]:
                self._delete_unlocked(key)
                return None
            return record["value"]

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        with self._mutex:
            expires_at = time.time() + ttl_seconds if ttl_seconds is not None else None
            raw_tags = getattr(value, "tags", None) or []
            if isinstance(raw_tags, str):
                tags = [raw_tags]
            elif hasattr(raw_tags, "__dataclass_fields__"):
                # Tags stored as a dataclass (e.g. CacheTags) -> collapse to strings.
                tags = [f"{k}:{getattr(raw_tags, k, None) or 'none'}" for k in raw_tags.__dict__]
            else:
                tags = [str(t) for t in raw_tags]
            self._data[key] = {"value": value, "expires_at": expires_at, "tags": tags}
            for tag in tags:
                self._tag_index.setdefault(tag, set()).add(key)

    async def delete(self, key: str) -> bool:
        with self._mutex:
            if key not in self._data:
                return False
            self._delete_unlocked(key)
            return True

    async def invalidate_tag(self, tag: str) -> int:
        """Delete all keys carrying ``tag``.  Returns count deleted."""
        with self._mutex:
            keys = list(self._tag_index.get(tag, set()))
            for key in keys:
                self._delete_unlocked(key)
            return len(keys)

    async def touch(self, key: str, ttl_seconds: int) -> bool:
        with self._mutex:
            record = self._data.get(key)
            if record is None:
                return False
            record["expires_at"] = time.time() + ttl_seconds
            return True

    def _delete_unlocked(self, key: str) -> None:
        record = self._data.pop(key, None)
        if record is None:
            return
        for tag in record.get("tags", []):
            index = self._tag_index.get(tag)
            if index is None:
                continue
            index.discard(key)
            if not index:
                self._tag_index.pop(tag, None)

    def snapshot_keys(self) -> List[str]:
        """Test helper exposing current key names."""
        with self._mutex:
            return list(self._data.keys())
