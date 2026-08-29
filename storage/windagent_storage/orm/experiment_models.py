"""SQLAlchemy ORM models for Experiment records (Phase 11 — ban_ke_hoach_v1 §17, §24)."""

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


class ExperimentORM(BaseORM):
    """SQLAlchemy model for empirical experiment records."""
    __tablename__ = "experiments"

    id = Column(String(64), primary_key=True)
    candidate_id = Column(String(64), nullable=False, index=True)
    baseline_harness_version = Column(String(64), nullable=False, index=True)
    experiment_type = Column(String(32), nullable=False, default="replay")
    status = Column(String(32), nullable=False, default="draft", index=True)

    dataset_id = Column(String(64), nullable=True)
    sample_size = Column(Integer, nullable=False, default=1)

    baseline_metrics_json = Column(Text, nullable=False, default="{}")
    candidate_metrics_json = Column(Text, nullable=False, default="{}")
    comparison_json = Column(Text, nullable=False, default="{}")

    safety_check_passed = Column(Boolean, nullable=False, default=False)
    reliability_check_passed = Column(Boolean, nullable=False, default=False)
    verdict = Column(String(32), nullable=False, default="inconclusive", index=True)

    project_id = Column(String(64), nullable=True, index=True)
    domain = Column(String(64), nullable=True, index=True)
    created_by = Column(String(64), nullable=False, default="system")
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_experiments_candidate_status", "candidate_id", "status"),
        Index("ix_experiments_proj_status", "project_id", "status"),
        Index("ix_experiments_domain_verdict", "domain", "verdict"),
        Index("ix_experiments_created_at", "created_at"),
    )

