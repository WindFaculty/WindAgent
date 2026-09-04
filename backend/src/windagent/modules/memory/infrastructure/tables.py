"""Durable tables for the Memory bounded context (Phase 14)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

memory_records_table = Table(
    "memory_records",
    metadata,
    Column("memory_id", String(36), primary_key=True),
    Column("scope", String(32), nullable=False),
    Column("key", String(256), nullable=False),
    Column("project_id", String(36), nullable=True),
    Column("session_id", String(36), nullable=True),
    Column("value_json", Text, nullable=False, default="{}"),
    Column("provenance_source", String(256), nullable=False, default=""),
    Column("tags_json", Text, nullable=False, default="{}"),
    Column("ttl_seconds", Integer, nullable=True),
    Column("content_hash", String(64), nullable=False, default=""),
    Column("learning_metadata_json", Text, nullable=False, default="{}"),
    Column("version", Integer, nullable=False, default=1),
    Column("optimistic_version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Index("ix_memory_records_scope", "scope"),
    Index("ix_memory_records_key", "key"),
    Index("ix_memory_records_project_id", "project_id"),
    Index("ix_memory_records_session_id", "session_id"),
    Index("ix_memory_records_content_hash", "content_hash"),
    Index("ix_memory_records_lookup", "scope", "key", "project_id", "session_id"),
)
