"""
Memory Models & Scopes for WindAgent Memory Package (Phase 21).
Includes working, session, project, user, and episodic scopes.
Supports TTL, content hashing for deduplication, and retention policies.
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, Optional


class MemoryScope(str, Enum):
    WORKING = "working"
    SESSION = "session"
    PROJECT = "project"
    USER = "user"
    EPISODIC = "episodic"


# Default TTL per scope (in seconds). None = no TTL (persistent)
DEFAULT_SCOPE_TTL: Dict[MemoryScope, Optional[int]] = {
    MemoryScope.WORKING: 3600,      # 1 hour
    MemoryScope.SESSION: 86400,     # 24 hours
    MemoryScope.PROJECT: None,      # Persistent (no TTL)
    MemoryScope.USER: None,         # Persistent
    MemoryScope.EPISODIC: 604800,   # 7 days
}


@dataclass
class MemoryRecord:
    id: str
    scope: MemoryScope
    key: str
    value: Any
    provenance_source: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    ttl_seconds: Optional[int] = None  # Override default TTL; None = use scope default
    content_hash: Optional[str] = None  # SHA256 for deduplication
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        """Computes SHA256 hash of key + value for deduplication."""
        raw = json.dumps({"key": self.key, "value": self.value}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_effective_ttl(self) -> Optional[int]:
        """Returns effective TTL: explicit override, scope default, or None (persistent)."""
        if self.ttl_seconds is not None:
            return self.ttl_seconds
        return DEFAULT_SCOPE_TTL.get(self.scope)

    def is_expired(self, reference_time: Optional[datetime] = None) -> bool:
        """Checks if this record has expired based on TTL."""
        ttl = self.get_effective_ttl()
        if ttl is None:
            return False  # No TTL = never expires
        ref = reference_time or datetime.now(timezone.utc)
        expiry = self.updated_at + timedelta(seconds=ttl)
        return ref >= expiry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope.value,
            "key": self.key,
            "value": self.value,
            "provenance_source": self.provenance_source,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": self.tags,
            "ttl_seconds": self.ttl_seconds,
            "content_hash": self.content_hash or self.compute_content_hash(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RetentionPolicy:
    """Declares retention rules for memory records."""
    max_records_per_scope: Optional[int] = None  # None = unlimited
    ttl_overrides: Dict[str, Optional[int]] = field(default_factory=dict)  # scope -> ttl_seconds
    auto_evict_expired: bool = True
