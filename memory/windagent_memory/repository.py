"""
Durable Memory Record Repository for WindAgent Memory Package (Phase 21).

Phase 3 (Dependency Inversion): the memory package no longer imports storage or
SQLAlchemy. ``MemoryRecordRepository`` is a domain-facing adapter over the
``MemoryRecordRepositoryPort`` from core. The concrete SQL implementation lives
in storage and is injected by composition roots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from windagent_memory.models import MemoryRecord, MemoryScope, RetentionPolicy
from windagent_core.contracts.repositories.memory_repository import (
    MemoryRecordRepositoryPort,
)

logger = logging.getLogger("windagent.memory.repository")


def _record_to_dict(record: MemoryRecord) -> Dict[str, Any]:
    """Converts domain MemoryRecord to a storage-safe dict (JSON-serializable)."""
    value_raw = record.value if isinstance(record.value, str) else json.dumps(record.value)
    return {
        "id": record.id,
        "scope": record.scope.value,
        "key": record.key,
        "value": value_raw,
        "provenance_source": record.provenance_source,
        "project_id": record.project_id,
        "session_id": record.session_id,
        "tags": record.tags,
        "ttl_seconds": record.ttl_seconds,
        "content_hash": record.content_hash or record.compute_content_hash(),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _dict_to_record(data: Dict[str, Any]) -> MemoryRecord:
    """Converts a storage dict back to a domain MemoryRecord."""
    value_raw = data.get("value", {})
    try:
        parsed = json.loads(value_raw) if isinstance(value_raw, str) else value_raw
    except ValueError:
        parsed = value_raw
    scope_str = str(data.get("scope", "session")).upper()
    try:
        scope = MemoryScope(scope_str.lower())
    except ValueError:
        scope = MemoryScope.SESSION

    def _as_dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    return MemoryRecord(
        id=str(data.get("id", "")),
        scope=scope,
        key=str(data.get("key", "")),
        value=parsed,
        provenance_source=str(data.get("provenance_source", "storage")),
        project_id=data.get("project_id"),
        session_id=data.get("session_id"),
        tags=dict(data.get("tags") or {}),
        ttl_seconds=data.get("ttl_seconds"),
        content_hash=data.get("content_hash"),
        created_at=_as_dt(data.get("created_at")),
        updated_at=_as_dt(data.get("updated_at")),
    )


class MemoryRecordRepository:
    """Durable repository for memory records backed by an injected port."""

    def __init__(self, port: MemoryRecordRepositoryPort):
        self._port = port

    async def save(self, record: MemoryRecord) -> None:
        """Persists a memory record (upsert)."""
        await self._port.save(_record_to_dict(record))
        logger.debug(f"Persisted memory record [{record.key}] scope={record.scope.value}")

    async def get_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieves a memory record by ID."""
        data = await self._port.get_by_id(record_id)
        return _dict_to_record(data) if data else None

    async def get_by_key(self, scope: MemoryScope, key: str, session_id: Optional[str] = None) -> Optional[MemoryRecord]:
        """Retrieves a memory record by scope + key + optional session_id."""
        data = await self._port.get_by_key(scope.value, key, session_id)
        return _dict_to_record(data) if data else None

    async def delete(self, record_id: str) -> bool:
        """Deletes a memory record by ID."""
        return await self._port.delete(record_id)

    async def delete_by_key(self, scope: MemoryScope, key: str, session_id: Optional[str] = None) -> bool:
        """Deletes a memory record by scope + key."""
        return await self._port.delete_by_key(scope.value, key, session_id)

    async def list_by_session(self, session_id: str) -> List[MemoryRecord]:
        """Lists all memory records for a session."""
        rows = await self._port.list_by_session(session_id)
        return [_dict_to_record(o) for o in rows]

    async def list_by_scope(self, scope: MemoryScope, limit: int = 100) -> List[MemoryRecord]:
        """Lists memory records for a given scope."""
        rows = await self._port.list_by_scope(scope.value, limit=limit)
        return [_dict_to_record(o) for o in rows]

    async def evict_expired(self, policy: RetentionPolicy) -> int:
        """Evicts expired memory records based on TTL and retention policy.
        Returns count of evicted records.
        """
        if not policy.auto_evict_expired:
            return 0

        rows = await self._port.list_by_scope("working", limit=10000)
        now = datetime.now(timezone.utc)
        evicted_count = 0
        for data in rows:
            record = _dict_to_record(data)
            if record.is_expired(reference_time=now):
                if await self.delete(record.id):
                    evicted_count += 1

        if evicted_count > 0:
            logger.info(f"Evicted {evicted_count} expired/stale memory records from durable storage.")

        return evicted_count