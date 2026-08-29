"""SQLAlchemy ORM models for Promotion Decision records (Phase 11 — ban_ke_hoach_v1 §17, §24, §35)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
)

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PromotionDecisionORM(BaseORM):
    """SQLAlchemy model for promotion decision records and audit history."""
    __tablename__ = "promotion_decisions"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    experiment_id = Column(String(64), nullable=True, index=True)
    source_harness_version = Column(String(64), nullable=False, index=True)
    target_harness_version = Column(String(64), nullable=True, index=True)

    status = Column(String(32), nullable=False, default="pending_approval", index=True)
    gate_checks_json = Column(Text, nullable=False, default="{}")

    is_high_risk = Column(Boolean, nullable=False, default=False)
    requires_human_approval = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    rejection_reason = Column(Text, nullable=True)
    decision_rationale = Column(Text, nullable=False, default="")

    project_id = Column(String(64), nullable=True, index=True)
    domain = Column(String(64), nullable=True, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_promotion_cand_status", "candidate_id", "status"),
        Index("ix_promotion_proj_status", "project_id", "status"),
        Index("ix_promotion_source_target", "source_harness_version", "target_harness_version"),
        Index("ix_promotion_created_at", "created_at"),
    )

