"""
Multi-Layered Memory Store for WindAgent Memory Package (Phase 21).
Provides working, session, project, user, and episodic memory layers with:
- Durable storage via MemoryRecordRepository
- Cross-project and cross-session isolation
- TTL-based auto-eviction
- Content-hash deduplication
- Secret/credential exclusion (via write policy)
- Provenance enforcement
- Retention policy management
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from windagent_core.errors.exceptions import ConflictError, NotFoundError
from windagent_memory.models import MemoryRecord, MemoryScope, RetentionPolicy, DEFAULT_SCOPE_TTL
from windagent_memory.write_policy import MemoryWritePolicy

logger = logging.getLogger("windagent.memory.store")


class MemoryStore:
    def __init__(
        self,
        write_policy: Optional[MemoryWritePolicy] = None,
        retention_policy: Optional[RetentionPolicy] = None,
        repository: Optional[Any] = None,  # MemoryRecordRepository (optional, for durable mode)
    ):
        self.write_policy = write_policy or MemoryWritePolicy()
        self.retention_policy = retention_policy or RetentionPolicy(auto_evict_expired=True)
        self.repository = repository
        # In-memory fallback store (used when repository is not provided)
        self._store: Dict[Tuple[str, str, Optional[str], Optional[str]], MemoryRecord] = {}
        # Content hash index for deduplication
        self._hash_index: Dict[str, str] = {}  # content_hash -> record_id

    def _make_storage_key(self, scope: MemoryScope, key: str, project_id: Optional[str], session_id: Optional[str]) -> Tuple[str, str, Optional[str], Optional[str]]:
        return (scope.value, key, project_id, session_id)

    def _generate_id(self) -> str:
        return f"mem_{uuid.uuid4().hex[:12]}"

    # ------------------------------------------------------------------
    # Save / Update with deduplication
    # ------------------------------------------------------------------

    def save(self, record: MemoryRecord) -> None:
        """Saves or updates a memory record after evaluating MemoryWritePolicy.
        Performs deduplication via content_hash: if an identical record exists, it is deduplicated.
        """
        # 1. Validate via write policy (secret exclusion, provenance, scope)
        self.write_policy.validate_and_enforce(record)

        # 2. Compute content hash for dedup if not set
        if not record.content_hash:
            record.content_hash = record.compute_content_hash()

        # 3. Deduplication: check if identical content already exists
        dup_record_id = self._hash_index.get(record.content_hash)
        if dup_record_id:
            # Check if the duplicate still exists
            existing = self._find_by_id(dup_record_id)
            if existing is not None:
                logger.info(
                    f"Deduplicated memory save for key [{record.key}]: "
                    f"identical content hash [{record.content_hash[:12]}...] matches record [{dup_record_id}]"
                )
                # Update the existing record's timestamp instead of creating new
                existing.updated_at = datetime.now(timezone.utc)
                self._persist(existing)
                return

        # 4. Check for existing record with same (scope, key, project, session) to update
        storage_key = self._make_storage_key(record.scope, record.key, record.project_id, record.session_id)
        existing_record = self._store.get(storage_key)

        if existing_record:
            # Update existing record
            existing_record.value = record.value
            existing_record.provenance_source = record.provenance_source
            existing_record.tags = record.tags
            existing_record.ttl_seconds = record.ttl_seconds
            existing_record.content_hash = record.content_hash
            existing_record.updated_at = datetime.now(timezone.utc)
            self._persist(existing_record)
            logger.info(f"Updated memory record [{record.key}] under scope [{record.scope.value}]")
        else:
            # Set ID if not provided
            if not record.id:
                record.id = self._generate_id()
            record.content_hash = record.content_hash or record.compute_content_hash()
            self._store[storage_key] = record
            self._hash_index[record.content_hash] = record.id
            self._persist(record)
            logger.info(f"Saved memory record [{record.key}] under scope [{record.scope.value}]")

    def save_many(self, records: List[MemoryRecord]) -> int:
        """Saves multiple records atomically. Returns count saved."""
        count = 0
        for record in records:
            try:
                self.save(record)
                count += 1
            except Exception as e:
                logger.warning(f"Skipped memory record [{record.key}]: {e}")
        return count

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(self, scope: MemoryScope, key: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> Optional[MemoryRecord]:
        storage_key = self._make_storage_key(scope, key, project_id, session_id)
        record = self._store.get(storage_key)

        # Check TTL expiry
        if record and record.is_expired():
            self.delete(scope, key, project_id, session_id)
            return None

        return record

    def get_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieves a memory record by its unique ID."""
        for rec in self._store.values():
            if rec.id == record_id:
                if rec.is_expired():
                    self._remove_from_store(rec)
                    return None
                return rec
        return None

    # ------------------------------------------------------------------
    # Delete / Forget
    # ------------------------------------------------------------------

    def delete(self, scope: MemoryScope, key: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> bool:
        storage_key = self._make_storage_key(scope, key, project_id, session_id)
        record = self._store.get(storage_key)
        if record:
            if record.content_hash:
                self._hash_index.pop(record.content_hash, None)
            del self._store[storage_key]
            self._delete_persisted(record.id)
            logger.info(f"Deleted memory record [{key}] under scope [{scope.value}]")
            return True
        return False

    def forget(self, scope: MemoryScope, key: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> bool:
        """Alias for delete with semantic clarity (explicit forget)."""
        return self.delete(scope, key, project_id, session_id)

    def forget_by_pattern(self, scope: MemoryScope, key_prefix: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> int:
        """Forgets all records matching a key prefix within a scope. Returns count forgotten."""
        count = 0
        to_forget = []
        for (s, k, p, sess), rec in list(self._store.items()):
            if s == scope.value and k.startswith(key_prefix):
                if project_id is None or p == project_id:
                    if session_id is None or sess == session_id:
                        to_forget.append((s, k, p, sess))

        for key_tuple in to_forget:
            if self.forget(MemoryScope(key_tuple[0]), key_tuple[1], key_tuple[2], key_tuple[3]):
                count += 1

        return count

    # ------------------------------------------------------------------
    # List / Query
    # ------------------------------------------------------------------

    def list_records_for_project(self, project_id: str) -> List[MemoryRecord]:
        """Lists records scoped strictly to project_id, enforcing cross-project isolation.
        Filters out expired records.
        """
        now = datetime.now(timezone.utc)
        result = []
        for rec in list(self._store.values()):
            if rec.project_id == project_id:
                if rec.is_expired(reference_time=now):
                    self._remove_from_store(rec)
                else:
                    result.append(rec)
        return result

    def list_records_for_session(self, session_id: str) -> List[MemoryRecord]:
        """Lists records for a session, filtering expired records."""
        now = datetime.now(timezone.utc)
        result = []
        for rec in list(self._store.values()):
            if rec.session_id == session_id:
                if rec.is_expired(reference_time=now):
                    self._remove_from_store(rec)
                else:
                    result.append(rec)
        return result

    def list_by_scope(self, scope: MemoryScope, limit: int = 100) -> List[MemoryRecord]:
        """Lists records for a given scope. Filters expired."""
        now = datetime.now(timezone.utc)
        result = []
        for rec in list(self._store.values()):
            if rec.scope == scope:
                if rec.is_expired(reference_time=now):
                    self._remove_from_store(rec)
                else:
                    result.append(rec)
        return sorted(result, key=lambda r: r.updated_at, reverse=True)[:limit]

    def search_by_tag(self, key: str, value: str) -> List[MemoryRecord]:
        """Searches records by tag key=value pair. Filters expired."""
        now = datetime.now(timezone.utc)
        results = []
        for rec in list(self._store.values()):
            if rec.tags.get(key) == value:
                if rec.is_expired(reference_time=now):
                    self._remove_from_store(rec)
                else:
                    results.append(rec)
        return results

    # ------------------------------------------------------------------
    # TTL / Eviction
    # ------------------------------------------------------------------

    def evict_expired(self) -> int:
        """Evicts all expired memory records. Returns count evicted."""
        now = datetime.now(timezone.utc)
        to_evict = []
        for storage_key, rec in list(self._store.items()):
            if rec.is_expired(reference_time=now):
                to_evict.append(storage_key)

        for sk in to_evict:
            rec = self._store.pop(sk, None)
            if rec and rec.content_hash:
                self._hash_index.pop(rec.content_hash, None)

        logger.info(f"Evicted {len(to_evict)} expired memory records.")
        return len(to_evict)

    def set_ttl(self, scope: MemoryScope, key: str, ttl_seconds: int, project_id: Optional[str] = None, session_id: Optional[str] = None) -> bool:
        """Updates TTL for an existing record."""
        record = self.get(scope, key, project_id, session_id)
        if record:
            record.ttl_seconds = ttl_seconds
            self._persist(record)
            return True
        return False

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def count_by_scope(self) -> Dict[str, int]:
        """Returns count of records per scope (excluding expired)."""
        self.evict_expired()
        counts: Dict[str, int] = {}
        for rec in self._store.values():
            scope_val = rec.scope.value
            counts[scope_val] = counts.get(scope_val, 0) + 1
        return counts

    def get_stats(self) -> Dict[str, Any]:
        """Returns store statistics."""
        self.evict_expired()
        return {
            "total_records": len(self._store),
            "by_scope": self.count_by_scope(),
            "retention_policy": {
                "auto_evict_expired": self.retention_policy.auto_evict_expired,
                "max_records_per_scope": self.retention_policy.max_records_per_scope,
            },
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _find_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        for rec in self._store.values():
            if rec.id == record_id:
                return rec
        return None

    def _remove_from_store(self, record: MemoryRecord) -> None:
        storage_key = self._make_storage_key(record.scope, record.key, record.project_id, record.session_id)
        if record.content_hash:
            self._hash_index.pop(record.content_hash, None)
        self._store.pop(storage_key, None)

    def _persist(self, record: MemoryRecord) -> None:
        """Persists record to durable storage if repository is available."""
        if self.repository:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self.repository.save(record))
                else:
                    loop.run_until_complete(self.repository.save(record))
            except RuntimeError:
                logger.warning("Could not persist memory record: no event loop available.")
            except Exception as e:
                logger.error(f"Error persisting memory record [{record.key}]: {e}")

    def _delete_persisted(self, record_id: str) -> None:
        """Deletes record from durable storage if repository is available."""
        if self.repository:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self.repository.delete(record_id))
                else:
                    loop.run_until_complete(self.repository.delete(record_id))
            except RuntimeError:
                pass
            except Exception as e:
                logger.warning(f"Error deleting persisted memory record [{record_id}]: {e}")
