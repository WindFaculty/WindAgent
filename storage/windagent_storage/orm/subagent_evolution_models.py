"""SQLAlchemy ORM models for Subagent Evolution records (Phase 13 — ban_ke_hoach_v1 §19, §24, §25)."""

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


class SubagentCandidateORM(BaseORM):
    """SQLAlchemy model for proposed subagent evolution candidates."""
    __tablename__ = "subagent_candidates"

    id = Column(String(64), primary_key=True)
    role = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="proposed", index=True)
    risk_level = Column(String(32), nullable=False, default="low")
    is_high_risk = Column(Boolean, nullable=False, default=False)

    proposed_spec_json = Column(Text, nullable=False, default="{}")
    reasoning_summary = Column(Text, nullable=False, default="")
    supporting_experiences_json = Column(Text, nullable=False, default="[]")

    security_audit_json = Column(Text, nullable=True)
    evaluation_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_subagent_cand_role_status", "role", "status"),
        Index("ix_subagent_cand_created_at", "created_at"),
    )


class SubagentSpecVersionORM(BaseORM):
    """SQLAlchemy model for versioned, declarative subagent configurations."""
    __tablename__ = "subagent_spec_versions"

    id = Column(String(64), primary_key=True)
    role = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False, index=True)
    parent_version = Column(String(64), nullable=True)

    objective = Column(Text, nullable=False, default="")
    system_supplement = Column(Text, nullable=False, default="")
    allowed_tools_json = Column(Text, nullable=False, default="[]")
    allowed_skills_json = Column(Text, nullable=False, default="[]")
    model_routing_policy_json = Column(Text, nullable=False, default="{}")
    memory_access_json = Column(Text, nullable=False, default="{}")
    max_budget_json = Column(Text, nullable=False, default="{}")
    max_depth = Column(Integer, nullable=False, default=2)
    output_contract_json = Column(Text, nullable=False, default="{}")

    status = Column(String(32), nullable=False, default="active", index=True)
    risk_level = Column(String(32), nullable=False, default="low")
    spec_hash = Column(String(64), nullable=True)

    promoted_from_candidate_id = Column(String(64), nullable=True, index=True)
    security_audit_id = Column(String(64), nullable=True)
    evaluation_id = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_subagent_spec_role_status", "role", "status"),
        Index("ix_subagent_spec_role_version", "role", "version"),
        Index("ix_subagent_spec_created_at", "created_at"),
    )


class SubagentPromotionDecisionORM(BaseORM):
    """SQLAlchemy model for subagent promotion decisions and rollback audits."""
    __tablename__ = "subagent_promotion_decisions"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    role = Column(String(64), nullable=False, index=True)
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
        Index("ix_subagent_prom_role_status", "role", "status"),
        Index("ix_subagent_prom_cand_status", "candidate_id", "status"),
        Index("ix_subagent_prom_created_at", "created_at"),
    )

