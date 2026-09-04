"""Application view models and durable row types for the Memory module (Phase 14)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..domain.models import LearningMetadata, MemoryRecord
from ..domain.scope import MemoryScope


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class MemoryRecordRow:
    memory_id: str
    scope: str
    key: str
    project_id: str | None
    session_id: str | None
    value_json: str
    provenance_source: str
    tags_json: str
    ttl_seconds: int | None
    content_hash: str
    learning_metadata_json: str
    version: int
    optimistic_version: int
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class MemoryRecordView:
    id: str
    scope: str
    key: str
    value: Any
    provenance_source: str
    project_id: str | None
    session_id: str | None
    tags: dict[str, str] = field(default_factory=dict)
    ttl_seconds: int | None = None
    content_hash: str = ""
    learning_metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    optimistic_version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope,
            "key": self.key,
            "value": self.value,
            "provenance_source": self.provenance_source,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": dict(self.tags),
            "ttl_seconds": self.ttl_seconds,
            "content_hash": self.content_hash,
            "learning_metadata": dict(self.learning_metadata),
            "version": self.version,
            "optimistic_version": self.optimistic_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: MemoryRecordRow) -> MemoryRecordView:
        try:
            val = json.loads(row.value_json)
        except Exception:
            val = row.value_json

        try:
            tags = json.loads(row.tags_json)
        except Exception:
            tags = {}

        try:
            learning_meta = json.loads(row.learning_metadata_json)
        except Exception:
            learning_meta = {}

        return cls(
            id=row.memory_id,
            scope=row.scope,
            key=row.key,
            value=val,
            provenance_source=row.provenance_source,
            project_id=row.project_id,
            session_id=row.session_id,
            tags=dict(tags) if isinstance(tags, dict) else {},
            ttl_seconds=row.ttl_seconds,
            content_hash=row.content_hash,
            learning_metadata=dict(learning_meta) if isinstance(learning_meta, dict) else {},
            version=row.version,
            optimistic_version=row.optimistic_version,
            created_at=row.created_at.isoformat() if row.created_at else "",
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )

    @classmethod
    def from_domain(cls, record: MemoryRecord, optimistic_version: int = 1) -> MemoryRecordView:
        return cls(
            id=record.id,
            scope=record.scope.value,
            key=record.key,
            value=record.value,
            provenance_source=record.provenance_source,
            project_id=record.project_id,
            session_id=record.session_id,
            tags=dict(record.tags),
            ttl_seconds=record.ttl_seconds,
            content_hash=record.content_hash or record.compute_content_hash(),
            learning_metadata=record.learning_metadata.to_dict() if record.learning_metadata else {},
            version=record.version,
            optimistic_version=optimistic_version,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )

    def to_domain(self) -> MemoryRecord:
        try:
            scope_enum = MemoryScope(self.scope)
        except ValueError:
            scope_enum = MemoryScope.WORKING

        learning_meta = (
            LearningMetadata.from_dict(self.learning_metadata)
            if self.learning_metadata
            else LearningMetadata()
        )

        c_at = datetime.fromisoformat(self.created_at) if self.created_at else utc_now()
        u_at = datetime.fromisoformat(self.updated_at) if self.updated_at else utc_now()

        return MemoryRecord(
            id=self.id,
            scope=scope_enum,
            key=self.key,
            value=self.value,
            provenance_source=self.provenance_source,
            project_id=self.project_id,
            session_id=self.session_id,
            tags=dict(self.tags),
            ttl_seconds=self.ttl_seconds,
            content_hash=self.content_hash,
            learning_metadata=learning_meta,
            version=self.version,
            created_at=c_at,
            updated_at=u_at,
        )


@dataclass(frozen=True, slots=True)
class MemoryStatsView:
    total_records: int
    by_scope: dict[str, int]

    def to_payload(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "by_scope": dict(self.by_scope),
        }
