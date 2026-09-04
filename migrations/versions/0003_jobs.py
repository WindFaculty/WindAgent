"""Durable jobs, fenced leases, and execution attempts (Phase 7).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep this historical schema immutable.  Phase 10 adds tracing columns
    # in 0004; importing the live Table here would make clean installs create
    # future columns before their owning revision runs.
    op.create_table(
        "platform_jobs",
        sa.Column("queue_position", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=255), nullable=False),
        sa.Column("job_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_s", sa.Float(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=255), nullable=True),
        sa.Column("fencing_token", sa.String(length=255), nullable=True),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancellation_requested_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.CheckConstraint("job_version >= 1", name="job_version_positive"),
        sa.CheckConstraint("attempt_count >= 0", name="job_attempt_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="job_max_attempts_positive"),
        sa.CheckConstraint(
            "lease_generation >= 0", name="job_lease_generation_non_negative"
        ),
        sa.PrimaryKeyConstraint("queue_position", name="pk_platform_jobs"),
        sa.UniqueConstraint("id", name="uq_platform_jobs_id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_platform_jobs_idempotency_key"
        ),
    )
    op.create_index(
        "ix_platform_jobs_claim",
        "platform_jobs",
        ["status", "available_at", "priority", "queue_position"],
        unique=False,
    )
    op.create_index(
        "ix_platform_jobs_expired_lease",
        "platform_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )
    op.create_table(
        "platform_job_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("fencing_token", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("attempt >= 1", name="job_attempt_number_positive"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["platform_jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_job_attempts"),
        sa.UniqueConstraint(
            "job_id", "attempt", name="uq_platform_job_attempts_job_attempt"
        ),
        sa.UniqueConstraint(
            "fencing_token", name="uq_platform_job_attempts_fencing_token"
        ),
    )
    op.create_index(
        "ix_platform_job_attempts_job_id",
        "platform_job_attempts",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("platform_job_attempts")
    op.drop_table("platform_jobs")
