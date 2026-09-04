"""Memory domain models, metadata, and retention rules (Phase 14)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .scope import (
    DEFAULT_SCOPE_TTL,
    TERMINAL_VALIDATION_STATUSES,
    VALIDATED_STATUSES,
    MemoryScope,
    ValidationStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def compute_content_hash(key: str, value: Any) -> str:
    """Computes deterministic SHA-256 hash of key + value."""
    try:
        raw = json.dumps({"key": key, "value": value}, sort_keys=True, default=str)
    except Exception:
        raw = f"{key}:{value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LearningMetadata:
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    sample_size: int = 0
    source_run_ids: tuple[str, ...] = ()
    harness_version: str | None = None
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    last_validated_at: datetime | None = None
    supersedes_id: str | None = None

    def is_validated(self) -> bool:
        return self.validation_status in VALIDATED_STATUSES

    def is_terminal(self) -> bool:
        return self.validation_status in TERMINAL_VALIDATION_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_refs": list(self.evidence_refs),
            "confidence": float(self.confidence),
            "sample_size": int(self.sample_size),
            "source_run_ids": list(self.source_run_ids),
            "harness_version": self.harness_version,
            "validation_status": self.validation_status.value,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "supersedes_id": self.supersedes_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LearningMetadata:
        if not data:
            return cls()

        status_val = data.get("validation_status", ValidationStatus.UNVALIDATED.value)
        try:
            status = ValidationStatus(status_val)
        except ValueError:
            status = ValidationStatus.UNVALIDATED

        last_val_at = None
        last_val_raw = data.get("last_validated_at")
        if last_val_raw:
            try:
                last_val_at = datetime.fromisoformat(last_val_raw)
            except Exception:
                pass

        return cls(
            evidence_refs=tuple(str(x) for x in data.get("evidence_refs", ())),
            confidence=float(data.get("confidence", 0.0)),
            sample_size=int(data.get("sample_size", 0)),
            source_run_ids=tuple(str(x) for x in data.get("source_run_ids", ())),
            harness_version=data.get("harness_version"),
            validation_status=status,
            last_validated_at=last_val_at,
            supersedes_id=data.get("supersedes_id"),
        )


@dataclass(slots=True)
class MemoryRecord:
    id: str
    scope: MemoryScope
    key: str
    value: Any
    provenance_source: str
    project_id: str | None = None
    session_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    ttl_seconds: int | None = None  # Override default TTL; None = use scope default
    content_hash: str | None = None  # SHA256 for deduplication
    learning_metadata: LearningMetadata = field(default_factory=LearningMetadata)
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def compute_content_hash(self) -> str:
        """Computes SHA256 hash of key + value for deduplication."""
        return compute_content_hash(self.key, self.value)

    def get_effective_ttl(self) -> int | None:
        """Returns effective TTL: explicit override, scope default, or None (persistent)."""
        if self.ttl_seconds is not None:
            return self.ttl_seconds
        return DEFAULT_SCOPE_TTL.get(self.scope)

    def is_expired(self, reference_time: datetime | None = None) -> bool:
        """Checks if this record has expired based on TTL."""
        ttl = self.get_effective_ttl()
        if ttl is None:
            return False  # Persistent
        ref = reference_time or utc_now()
        expiry = self.updated_at + timedelta(seconds=ttl)
        return ref >= expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope.value,
            "key": self.key,
            "value": self.value,
            "provenance_source": self.provenance_source,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": dict(self.tags),
            "ttl_seconds": self.ttl_seconds,
            "content_hash": self.content_hash or self.compute_content_hash(),
            "learning_metadata": self.learning_metadata.to_dict(),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        created_at_raw = data.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else utc_now()
        updated_at_raw = data.get("updated_at")
        updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else utc_now()

        scope_val = data.get("scope", MemoryScope.WORKING.value)
        try:
            scope = MemoryScope(scope_val)
        except ValueError:
            scope = MemoryScope.WORKING

        learning_data = data.get("learning_metadata")
        learning_meta = LearningMetadata.from_dict(learning_data) if isinstance(learning_data, dict) else LearningMetadata()

        return cls(
            id=str(data.get("id", "")),
            scope=scope,
            key=str(data.get("key", "")),
            value=data.get("value"),
            provenance_source=str(data.get("provenance_source", "")),
            project_id=data.get("project_id"),
            session_id=data.get("session_id"),
            tags=dict(data.get("tags") or {}),
            ttl_seconds=data.get("ttl_seconds"),
            content_hash=data.get("content_hash"),
            learning_metadata=learning_meta,
            version=int(data.get("version", 1)),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass(slots=True)
class RetentionPolicy:
    """Declares retention rules for memory records."""
    max_records_per_scope: int | None = None  # None = unlimited
    ttl_overrides: dict[str, int | None] = field(default_factory=dict)
    auto_evict_expired: bool = True
