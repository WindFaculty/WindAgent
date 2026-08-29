"""SQLAlchemy ORM models for Experience Store records (Phase 8 — ban_ke_hoach_v1 §13 & §24)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
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


class ExperienceRecordORM(BaseORM):
    __tablename__ = "experience_records"

    id = Column(String(64), primary_key=True)
    execution_id = Column(String(64), nullable=False, index=True)
    trajectory_id = Column(String(64), nullable=True, index=True)
    parent_task_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    state = Column(String(32), nullable=False, default="raw", index=True)

    # Telemetry JSON payloads
    context_json = Column(Text, nullable=False, default="{}")
    decision_json = Column(Text, nullable=False, default="{}")
    action_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=False, default="{}")
    artifacts_json = Column(Text, nullable=False, default="[]")
    metrics_json = Column(Text, nullable=False, default="{}")

    # Evaluation & Learning Attribution
    evaluator_results_json = Column(Text, nullable=False, default="[]")
    hypothesis = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    provenance_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now, onupdate=default_utc_now)

    __table_args__ = (
        Index("ix_experience_state_conf", "state", "confidence"),
        Index("ix_experience_proj_state", "project_id", "state"),
        Index("ix_experience_exec_state", "execution_id", "state"),
        Index("ix_experience_created_at", "created_at"),
    )

