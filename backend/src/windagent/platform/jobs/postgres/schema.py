"""SQL schema for durable jobs and their fenced execution attempts."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from windagent.platform.persistence.metadata import metadata

jobs_table = Table(
    "platform_jobs",
    metadata,
    Column("queue_position", Integer, primary_key=True, autoincrement=True),
    Column("id", String(36), nullable=False),
    Column("job_type", String(255), nullable=False),
    Column("job_version", Integer, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("priority", Integer, nullable=False, default=0),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False),
    Column("timeout_s", Float, nullable=True),
    Column("deadline", DateTime(timezone=True), nullable=True),
    Column("correlation_id", String(36), nullable=True),
    Column("causation_id", String(36), nullable=True),
    Column("trace_id", String(32), nullable=True),
    Column("actor_id", String(36), nullable=True),
    Column("status", String(32), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("claimed_by", String(255), nullable=True),
    Column("fencing_token", String(255), nullable=True),
    Column("lease_generation", Integer, nullable=False, default=0),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("cancellation_requested_at", DateTime(timezone=True), nullable=True),
    Column("result_json", Text, nullable=True),
    Column("last_error", Text, nullable=True),
    Column("idempotency_key", String(255), nullable=True),
    CheckConstraint("job_version >= 1", name="job_version_positive"),
    CheckConstraint("attempt_count >= 0", name="job_attempt_non_negative"),
    CheckConstraint("max_attempts >= 1", name="job_max_attempts_positive"),
    CheckConstraint("lease_generation >= 0", name="job_lease_generation_non_negative"),
    UniqueConstraint("id", name="uq_platform_jobs_id"),
    UniqueConstraint("idempotency_key", name="uq_platform_jobs_idempotency_key"),
)

Index(
    "ix_platform_jobs_claim",
    jobs_table.c.status,
    jobs_table.c.available_at,
    jobs_table.c.priority,
    jobs_table.c.queue_position,
)
Index(
    "ix_platform_jobs_expired_lease",
    jobs_table.c.status,
    jobs_table.c.lease_expires_at,
)


job_attempts_table = Table(
    "platform_job_attempts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "job_id",
        String(36),
        ForeignKey("platform_jobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("attempt", Integer, nullable=False),
    Column("worker_id", String(255), nullable=False),
    Column("fencing_token", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error", Text, nullable=True),
    CheckConstraint("attempt >= 1", name="job_attempt_number_positive"),
    UniqueConstraint("job_id", "attempt", name="uq_platform_job_attempts_job_attempt"),
    UniqueConstraint("fencing_token", name="uq_platform_job_attempts_fencing_token"),
)

Index("ix_platform_job_attempts_job_id", job_attempts_table.c.job_id)
