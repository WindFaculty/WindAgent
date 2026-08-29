"""SQLAlchemy ORM models for Evaluation Engine V2 records (Phase 7 - ban_ke_hoach_v1 §12)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
)

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationRecordORM(BaseORM):
    __tablename__ = "evaluation_records"

    id = Column(String(64), primary_key=True)
    execution_id = Column(String(64), nullable=False, index=True)
    trajectory_id = Column(String(64), nullable=False, index=True)
    evaluator_version = Column(String(32), nullable=False, default="2.0.0", index=True)
    harness_version = Column(String(32), nullable=True, index=True)
    dimension = Column(String(32), nullable=False, index=True)
    metric_name = Column(String(64), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    threshold = Column(Float, nullable=False, default=0.7)
    confidence = Column(Float, nullable=False, default=1.0)
    evidence_refs_json = Column(Text, nullable=False, default="[]")
    passed = Column(Boolean, nullable=False, default=False, index=True)
    blocked = Column(Boolean, nullable=False, default=False, index=True)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_evaluation_exec_metric", "execution_id", "metric_name"),
        Index("ix_evaluation_dim_score", "dimension", "score"),
        Index("ix_evaluation_harness_metric", "harness_version", "metric_name"),
    )

