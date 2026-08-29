"""SQLAlchemy ORM models for Memory V2 records (Phase 6 - ban_ke_hoach_v1 chapter 11)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRecordV2ORM(BaseORM):
    __tablename__ = "memory_v2_records"

    id = Column(String(64), primary_key=True)
    scope = Column(String(32), nullable=False, index=True)
    key = Column(String(128), nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    provenance_source = Column(String(128), nullable=False)
    project_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    tags_json = Column(Text, nullable=False, default="{}")
    ttl_seconds = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    evidence_refs_json = Column(Text, nullable=False, default="[]")
    confidence = Column(Float, nullable=False, default=0.0)
    sample_size = Column(Integer, nullable=False, default=0)
    source_run_ids_json = Column(Text, nullable=False, default="[]")
    harness_version = Column(String(32), nullable=True)
    validation_status = Column(String(32), nullable=False, default="unvalidated", index=True)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    supersedes_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_memory_v2_scope_key", "scope", "key"),
        Index("ix_memory_v2_scope_proj", "scope", "project_id"),
        Index("ix_memory_v2_scope_sess", "scope", "session_id"),
        Index("ix_memory_v2_status_conf", "validation_status", "confidence"),
    )
