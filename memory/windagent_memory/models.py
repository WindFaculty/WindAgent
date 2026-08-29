"""
Memory Models & Scopes for WindAgent Memory Package (Phase 21).
Includes working, session, project, user, and episodic scopes.
Supports TTL, content hashing for deduplication, and retention policies.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional


from windagent_core.domain.memory_v2 import (
    DEFAULT_SCOPE_TTL,
    LearningMetadata,
    MemoryRecordV2,
    MemoryScope,
    compute_content_hash,
)


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
    learning_metadata: Optional[LearningMetadata] = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        """Computes SHA256 hash of key + value for deduplication."""
        return compute_content_hash(self.key, self.value)

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

    def to_v2(self) -> MemoryRecordV2:
        return MemoryRecordV2(
            id=self.id,
            scope=self.scope,
            key=self.key,
            value=self.value,
            provenance_source=self.provenance_source,
            project_id=self.project_id,
            session_id=self.session_id,
            tags=dict(self.tags),
            ttl_seconds=self.ttl_seconds,
            content_hash=self.content_hash or self.compute_content_hash(),
            learning_metadata=self.learning_metadata or LearningMetadata(),
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_v2(cls, v2: MemoryRecordV2) -> MemoryRecord:
        return cls(
            id=v2.id,
            scope=v2.scope,
            key=v2.key,
            value=v2.value,
            provenance_source=v2.provenance_source,
            project_id=v2.project_id,
            session_id=v2.session_id,
            tags=dict(v2.tags),
            ttl_seconds=v2.ttl_seconds,
            content_hash=v2.content_hash,
            learning_metadata=v2.learning_metadata,
            version=v2.version,
            created_at=v2.created_at,
            updated_at=v2.updated_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = {
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
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.learning_metadata is not None:
            d["learning_metadata"] = self.learning_metadata.to_dict()
        return d


@dataclass
class RetentionPolicy:
    """Declares retention rules for memory records."""
    max_records_per_scope: Optional[int] = None  # None = unlimited
    ttl_overrides: Dict[str, Optional[int]] = field(default_factory=dict)  # scope -> ttl_seconds
    auto_evict_expired: bool = True
