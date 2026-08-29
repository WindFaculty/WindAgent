"""SQLAlchemy ORM models for Continual Harness records (Phase 10 — ban_ke_hoach_v1 §15, §16, §24)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HarnessVersionORM(BaseORM):
    """SQLAlchemy model for versioned continual harness snapshots."""
    __tablename__ = "harness_versions"

    id = Column(String(64), primary_key=True)
    version_number = Column(Integer, nullable=False)
    parent_version = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)

    entries_json = Column(Text, nullable=False, default="[]")
    diff_json = Column(Text, nullable=False, default="{}")
    evidence_json = Column(Text, nullable=False, default="[]")
    promotion_decision_json = Column(Text, nullable=False, default="{}")
    evaluation_set_json = Column(Text, nullable=False, default="{}")

    created_by = Column(String(64), nullable=False, default="system")
    project_id = Column(String(64), nullable=True, index=True)
    domain = Column(String(64), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_harness_version_proj_active", "project_id", "is_active"),
        Index("ix_harness_version_proj_status", "project_id", "status"),
        Index("ix_harness_version_domain_active", "domain", "is_active"),
        Index("ix_harness_version_number", "version_number"),
        Index("ix_harness_version_created_at", "created_at"),
    )


class RefinementProposalORM(BaseORM):
    """SQLAlchemy model for preview-first refinement proposals."""
    __tablename__ = "refinement_proposals"

    id = Column(String(64), primary_key=True)
    target_harness_version = Column(String(64), nullable=False, index=True)
    candidate_ids_json = Column(Text, nullable=False, default="[]")
    proposed_entries_json = Column(Text, nullable=False, default="[]")
    preview_diff_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="preview", index=True)

    evaluation_results_json = Column(Text, nullable=False, default="{}")
    project_id = Column(String(64), nullable=True, index=True)
    created_by = Column(String(64), nullable=False, default="system")
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_refinements_target_version", "target_harness_version"),
        Index("ix_refinements_proj_status", "project_id", "status"),
        Index("ix_refinements_created_at", "created_at"),
    )

