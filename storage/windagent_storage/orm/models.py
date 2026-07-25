"""
SQLAlchemy Declarative ORM Models for WindAgent Storage Layer.
Fully decoupled from windagent_core domain entities.
"""

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import DeclarativeBase, relationship


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseORM(DeclarativeBase):
    pass


class SessionORM(BaseORM):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True)
    title = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="idle")
    agent_id = Column(String(64), nullable=True)
    workspace_root = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)
    last_event_sequence = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)


class TaskORM(BaseORM):
    __tablename__ = "v2_tasks"

    id = Column(String(36), primary_key=True)
    prompt = Column(Text, nullable=False)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    tags_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class WorkflowRunORM(BaseORM):
    __tablename__ = "v2_workflow_runs"

    run_id = Column(String(36), primary_key=True)
    workflow_id = Column(String(36), nullable=False)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=default_utc_now)

    steps = relationship("WorkflowStepORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin")


class WorkflowStepORM(BaseORM):
    __tablename__ = "v2_workflow_steps"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("v2_workflow_runs.run_id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    tool_name = Column(String(64), nullable=False)
    params_json = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    run = relationship("WorkflowRunORM", back_populates="steps")


class ExecutionEventORM(BaseORM):
    __tablename__ = "execution_events"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(64), nullable=False)
    data_json = Column(Text, nullable=False)
    event_seq = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class OutboxRecordORM(BaseORM):
    __tablename__ = "v2_outbox_records"

    id = Column(String(36), primary_key=True)
    event_id = Column(String(36), nullable=False, index=True)
    aggregate_id = Column(String(36), nullable=True, index=True)
    aggregate_type = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    sequence_number = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    available_at = Column(DateTime, nullable=False, default=default_utc_now)
    published_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending, publishing, published, dead_letter
    deduplication_key = Column(String(128), nullable=True, unique=True)
    claimed_by = Column(String(64), nullable=True)
    claim_token = Column(String(64), nullable=True)
    claim_expires_at = Column(DateTime, nullable=True)


class OutboxReplayAuditORM(BaseORM):
    __tablename__ = "v2_outbox_replay_audit"

    id = Column(String(36), primary_key=True)
    outbox_record_id = Column(String(36), nullable=False, index=True)
    event_id = Column(String(36), nullable=False, index=True)
    replay_attempt_id = Column(String(64), nullable=False)
    operator = Column(String(128), nullable=True)
    previous_status = Column(String(32), nullable=False)
    previous_attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class ArtifactRefORM(BaseORM):
    __tablename__ = "v2_artifacts"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    uri = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    metadata_json = Column(Text, nullable=True)


class ProviderConfigORM(BaseORM):
    __tablename__ = "v2_provider_configs"

    id = Column(String(64), primary_key=True)
    provider_name = Column(String(64), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)
