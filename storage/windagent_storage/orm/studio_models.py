"""Studio persistence ORM models (Plan A — A3, studio.contract/v0.1).

Additive tables owned exclusively by the A3 migration
``0010_studio_persistence``. Importing this module registers the tables on
``BaseORM.metadata`` (used by tests and the ``create_all`` dev path); the
Alembic chain deliberately does NOT import it so the single ordered migration
stays the only producer of the Studio schema on real databases.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudioSeriesProjectORM(BaseORM):
    __tablename__ = "studio_series_projects"

    series_id = Column(String(64), primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    episode_ids_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    metadata_json = Column(Text, nullable=False, default="{}")


class StudioEpisodeORM(BaseORM):
    __tablename__ = "studio_episodes"

    episode_id = Column(String(64), primary_key=True)
    series_id = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    episode_number = Column(Integer, nullable=False, default=1)
    state = Column(String(32), nullable=False, default="DRAFT")
    current_revision_id = Column(String(64), nullable=True)
    active_run_id = Column(String(64), nullable=True)
    awaiting_checkpoint = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    optimistic_version = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("series_id", "episode_number", name="uq_studio_episode_series_number"),
    )


class StudioRevisionORM(BaseORM):
    __tablename__ = "studio_revisions"

    revision_id = Column(String(64), primary_key=True)
    series_id = Column(String(64), nullable=False, index=True)
    episode_id = Column(String(64), nullable=False, index=True)
    parent_revision_id = Column(String(64), nullable=True)
    creator = Column(String(128), nullable=False)
    actor = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    content_hash = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False, default="DRAFT")
    status = Column(String(32), nullable=False, default="DRAFT")
    lock_state = Column(String(32), nullable=False, default="UNLOCKED")
    invalidation_intent = Column(String(32), nullable=True)
    summary = Column(Text, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    optimistic_version = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("episode_id", "content_hash", name="uq_studio_revision_episode_hash"),
    )


class StudioArtifactORM(BaseORM):
    __tablename__ = "studio_artifacts"

    artifact_id = Column(String(64), primary_key=True)
    artifact_type = Column(String(64), nullable=False)
    schema_version = Column(String(64), nullable=False, default="studio.artifact/v1alpha1")
    series_id = Column(String(64), nullable=False, index=True)
    episode_id = Column(String(64), nullable=False, index=True)
    revision_id = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=False)
    input_artifact_refs_json = Column(Text, nullable=False, default="[]")
    prompt_id = Column(String(64), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    prompt_hash = Column(String(64), nullable=True)
    model_route_id = Column(String(64), nullable=True)
    provider_id = Column(String(64), nullable=True)
    model_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    created_by = Column(String(128), nullable=False, default="system")
    content_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_studio_artifact_hash"),
    )


class StudioApprovalPolicyORM(BaseORM):
    __tablename__ = "studio_approval_policies"

    policy_id = Column(String(64), primary_key=True)
    policy_version = Column(String(64), primary_key=True)
    checkpoint_to_mode_json = Column(Text, nullable=False, default="{}")
    quality_thresholds_json = Column(Text, nullable=False, default="{}")
    max_review_revision_iterations = Column(Integer, nullable=False, default=10)
    required_approver_roles_json = Column(Text, nullable=False, default='["OWNER"]')
    effective_time = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class StudioApprovalDecisionORM(BaseORM):
    __tablename__ = "studio_approval_decisions"

    approval_id = Column(String(64), primary_key=True)
    aggregate_id = Column(String(64), nullable=False, index=True)
    revision_id = Column(String(64), nullable=False, index=True)
    artifact_hash = Column(String(64), nullable=False)
    checkpoint = Column(String(64), nullable=False)
    actor = Column(String(128), nullable=False)
    role = Column(String(64), nullable=False, default="OWNER")
    decision = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False, default="")
    timestamp = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "revision_id", "checkpoint", "actor",
            name="uq_studio_approval_revision_checkpoint_actor",
        ),
    )


class StudioRunORM(BaseORM):
    __tablename__ = "studio_runs"

    run_id = Column(String(64), primary_key=True)
    series_id = Column(String(64), nullable=False, index=True)
    episode_id = Column(String(64), nullable=False, index=True)
    dag_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    metadata_json = Column(Text, nullable=False, default="{}")


class StudioRunNodeORM(BaseORM):
    """Durable per-node state of a Studio story run (Plan A — A4)."""

    __tablename__ = "studio_run_nodes"

    run_id = Column(String(64), primary_key=True)
    dag_node_id = Column(String(64), primary_key=True)
    task_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="PENDING")
    task_id = Column(String(64), nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    depends_on_json = Column(Text, nullable=False, default="[]")
    checkpoint = Column(String(64), nullable=True)
    gate = Column(Boolean, nullable=False, default=False)
    input_hashes_json = Column(Text, nullable=False, default="[]")
    output_hashes_json = Column(Text, nullable=False, default="[]")
    output_artifact_refs_json = Column(Text, nullable=False, default="[]")
    error = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_studio_run_nodes_status", "status"),
        Index("ix_studio_run_nodes_task_id", "task_id"),
    )


class StudioEventORM(BaseORM):
    __tablename__ = "studio_events"

    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(128), nullable=False, index=True)
    schema_version = Column(String(64), nullable=False, default="studio.event/v1")
    aggregate_id = Column(String(64), nullable=False, index=True)
    aggregate_type = Column(String(64), nullable=False, default="studio")
    sequence = Column(Integer, nullable=False, default=0)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    correlation_id = Column(String(64), nullable=True)
    causation_id = Column(String(64), nullable=True)
    studio_run_id = Column(String(64), nullable=True, index=True)
    revision_ref = Column(String(64), nullable=True)
    artifact_refs_json = Column(Text, nullable=False, default="[]")
    payload_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("aggregate_id", "sequence", name="uq_studio_event_aggregate_sequence"),
    )


__all__ = [
    "StudioSeriesProjectORM",
    "StudioEpisodeORM",
    "StudioRevisionORM",
    "StudioArtifactORM",
    "StudioApprovalPolicyORM",
    "StudioApprovalDecisionORM",
    "StudioRunORM",
    "StudioRunNodeORM",
    "StudioEventORM",
]
