"""
Multi-Layered Memory Store for WindAgent Memory Package.
Provides session, project, user, and episodic memory layers with cross-project isolation.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_memory.models import MemoryRecord, MemoryScope
from windagent_memory.write_policy import MemoryWritePolicy

logger = logging.getLogger("windagent.memory.store")


class MemoryStore:
    def __init__(self, write_policy: Optional[MemoryWritePolicy] = None):
        self.write_policy = write_policy or MemoryWritePolicy()
        self._store: Dict[Tuple[str, str, Optional[str], Optional[str]], MemoryRecord] = {}

    def _make_storage_key(self, scope: MemoryScope, key: str, project_id: Optional[str], session_id: Optional[str]) -> Tuple[str, str, Optional[str], Optional[str]]:
        return (scope.value, key, project_id, session_id)

    def save(self, record: MemoryRecord) -> None:
        """Saves or updates a memory record after evaluating MemoryWritePolicy."""
        self.write_policy.validate_and_enforce(record)
        storage_key = self._make_storage_key(record.scope, record.key, record.project_id, record.session_id)
        self._store[storage_key] = record
        logger.info(f"Saved memory record [{record.key}] under scope [{record.scope.value}]")

    def get(self, scope: MemoryScope, key: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> Optional[MemoryRecord]:
        storage_key = self._make_storage_key(scope, key, project_id, session_id)
        return self._store.get(storage_key)

    def delete(self, scope: MemoryScope, key: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> bool:
        storage_key = self._make_storage_key(scope, key, project_id, session_id)
        if storage_key in self._store:
            del self._store[storage_key]
            logger.info(f"Deleted memory record [{key}] under scope [{scope.value}]")
            return True
        return False

    def list_records_for_project(self, project_id: str) -> List[MemoryRecord]:
        """Lists records scoped strictly to project_id, enforcing cross-project isolation."""
        return [rec for rec in self._store.values() if rec.project_id == project_id]
