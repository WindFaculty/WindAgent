"""SQLAlchemy ORM models for Skill Evolution records (Phase 12 — ban_ke_hoach_v1 §18, §24, §25)."""

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


class SkillCandidateORM(BaseORM):
    """SQLAlchemy model for proposed skill evolution candidates."""
    __tablename__ = "skill_candidates"

    id = Column(String(64), primary_key=True)
    skill_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="proposed", index=True)
    risk_level = Column(String(32), nullable=False, default="low")
    is_executable = Column(Boolean, nullable=False, default=False)
    is_high_risk = Column(Boolean, nullable=False, default=False)

    proposed_manifest_json = Column(Text, nullable=False, default="{}")
    proposed_code = Column(Text, nullable=True)
    reasoning_summary = Column(Text, nullable=False, default="")
    supporting_experiences_json = Column(Text, nullable=False, default="[]")

    security_audit_json = Column(Text, nullable=True)
    evaluation_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_skill_cand_skill_status", "skill_id", "status"),
        Index("ix_skill_cand_created_at", "created_at"),
    )


class SkillVersionORM(BaseORM):
    """SQLAlchemy model for versioned and deployed skill states."""
    __tablename__ = "skill_versions"

    id = Column(String(64), primary_key=True)
    skill_id = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False, index=True)
    parent_version = Column(String(64), nullable=True)

    manifest_json = Column(Text, nullable=False, default="{}")
    code_hash = Column(String(64), nullable=True)
    source_code = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)

    promoted_from_candidate_id = Column(String(64), nullable=True, index=True)
    security_audit_id = Column(String(64), nullable=True)
    evaluation_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_skill_ver_skill_status", "skill_id", "status"),
        Index("ix_skill_ver_skill_version", "skill_id", "version"),
        Index("ix_skill_ver_created_at", "created_at"),
    )


class SkillPromotionDecisionORM(BaseORM):
    """SQLAlchemy model for skill promotion decision records and audits."""
    __tablename__ = "skill_promotion_decisions"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    skill_id = Column(String(64), nullable=False, index=True)
    source_version = Column(String(32), nullable=True)
    target_version = Column(String(32), nullable=False)

    status = Column(String(32), nullable=False, default="pending_approval", index=True)
    security_audit_passed = Column(Boolean, nullable=False, default=False)
    evaluation_passed = Column(Boolean, nullable=False, default=False)
    requires_human_approval = Column(Boolean, nullable=False, default=False)

    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    decision_rationale = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_skill_prom_skill_status", "skill_id", "status"),
        Index("ix_skill_prom_cand_status", "candidate_id", "status"),
        Index("ix_skill_prom_created_at", "created_at"),
    )

