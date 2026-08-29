"""ORM for durable Persistent Goals (Phase 5)."""
from __future__ import annotations
from sqlalchemy import Column, DateTime, Integer, String, Text
from windagent_storage.orm.models import BaseORM, default_utc_now

class PersistentGoalORM(BaseORM):
    __tablename__ = "persistent_goals"

    goal_id = Column(String(64), primary_key=True)
    objective = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE")
    progress_summary = Column(Text, nullable=False, default="")
    completion_criteria_json = Column(Text, nullable=False, default="{}")
    blocked_reason = Column(Text, nullable=True)
    conversation_id = Column(String(64), nullable=True, index=True)
    parent_task_id = Column(String(64), nullable=True, index=True)
    agent_run_id = Column(String(64), nullable=True, index=True)
    harness_version = Column(String(32), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    last_progress_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
