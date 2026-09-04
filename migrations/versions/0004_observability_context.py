"""Persist job trace and actor context (Phase 10).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_jobs", sa.Column("trace_id", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "platform_jobs", sa.Column("actor_id", sa.String(length=36), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("platform_jobs", "actor_id")
    op.drop_column("platform_jobs", "trace_id")
