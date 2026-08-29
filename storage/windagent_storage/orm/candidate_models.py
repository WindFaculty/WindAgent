"""SQLAlchemy ORM models for Candidate Learning records (Phase 9 — ban_ke_hoach_v1 §14, §23, §24)."""

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


class LearningCandidateORM(BaseORM):
    """SQLAlchemy model for proposed, eligible, and experimenting learning candidates."""
    __tablename__ = "learning_candidates"

    id = Column(String(64), primary_key=True)
    kind = Column(String(32), nullable=False)
    condition = Column(Text, nullable=False)
    proposed_change_json = Column(Text, nullable=False, default="{}")
    reasoning_summary = Column(Text, nullable=False)

    supporting_experiences_json = Column(Text, nullable=False, default="[]")
    counter_evidence_json = Column(Text, nullable=False, default="[]")
    sample_size = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=0.0)

    scope = Column(String(32), nullable=False, default="project")
    risk_level = Column(String(32), nullable=False, default="medium")
    status = Column(String(32), nullable=False, default="proposed", index=True)

    project_id = Column(String(64), nullable=True, index=True)
    domain = Column(String(64), nullable=True, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_candidate_status_conf", "status", "confidence"),
        Index("ix_candidate_proj_status", "project_id", "status"),
        Index("ix_candidate_domain_status", "domain", "status"),
        Index("ix_candidate_kind_status", "kind", "status"),
        Index("ix_candidate_created_at", "created_at"),
    )


class LearnedRuleORM(BaseORM):
    """SQLAlchemy model for structured learned rules (Phase 9 & Phase 14 — Organizational Learning)."""
    __tablename__ = "learned_rules"

    id = Column(String(64), primary_key=True)
    condition = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    domain = Column(String(64), nullable=False, default="general", index=True)
    scope = Column(String(32), nullable=False, default="project")
    target_role = Column(String(64), nullable=True, index=True)
    project_id = Column(String(64), nullable=True, index=True)

    evidence_refs_json = Column(Text, nullable=False, default="[]")
    metrics_json = Column(Text, nullable=False, default="{}")
    confidence = Column(Float, nullable=False, default=0.0)
    sample_size = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    harness_version = Column(String(64), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    state = Column(String(32), nullable=False, default="candidate", index=True)
    supersedes_id = Column(String(64), nullable=True)
    superseded_by = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=True, default="{}")

    __table_args__ = (
        Index("ix_rule_domain_state", "domain", "state"),
        Index("ix_rule_created_at", "created_at"),
        Index("ix_learned_rules_role_state", "target_role", "state"),
        Index("ix_learned_rules_project_state", "project_id", "state"),
    )

