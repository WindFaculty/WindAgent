"""
SQLAlchemy Declarative ORM Models for Video Production API V2 Foundation (Stage B).
"""

from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, Index, Integer, String, Text, UniqueConstraint
)

from windagent_storage.orm.models import BaseORM, default_utc_now


class ProductionProjectORM(BaseORM):
    __tablename__ = "video_production_projects"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False, default="Untitled Production")
    status = Column(String(32), nullable=False, default="ACTIVE")
    active_revision_id = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class ProductionRevisionORM(BaseORM):
    __tablename__ = "video_production_revisions"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False, index=True)
    parent_revision_id = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="DRAFT")
    content_hash = Column(String(128), nullable=False, default="")
    sequence = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("idx_vp_rev_project_seq", "project_id", "sequence"),
    )


class WorkspaceReadModelORM(BaseORM):
    __tablename__ = "video_production_workspace_read_models"

    project_id = Column(String(64), primary_key=True)
    projection_json = Column(Text, nullable=False, default="{}")
    current_sequence = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class IdempotencyRecordORM(BaseORM):
    __tablename__ = "video_production_idempotency_records"

    id = Column(String(64), primary_key=True)
    scope = Column(String(64), nullable=False, default="workspace_command")
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(128), nullable=False)
    response_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="COMPLETED")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
        Index("idx_idempotency_scope_key", "scope", "idempotency_key"),
    )


class ProductionEventORM(BaseORM):
    __tablename__ = "video_production_events"

    event_id = Column(String(64), primary_key=True)
    sequence = Column(Integer, nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    revision_id = Column(String(64), nullable=False, default="")
    event_type = Column(String(128), nullable=False)
    aggregate_type = Column(String(64), nullable=False, default="WORKSPACE")
    aggregate_id = Column(String(64), nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("idx_vp_event_project_seq", "project_id", "sequence"),
    )


class ProjectionCheckpointORM(BaseORM):
    __tablename__ = "video_production_projection_checkpoints"

    projector_id = Column(String(64), primary_key=True)
    last_sequence = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
