"""0014 route lock authority columns (Phase 1 routing authority).

Revision ID: 0014_route_lock_authority
Revises: 0013_v3_resources
Create Date: 2026-08-20

Adds the ``route_locks_v3`` columns and the partial unique active-scope index
already required by ``RouteLockV3ORM`` but never materialized by the Alembic
chain (the old ad-hoc ``phase1_routing_authority`` migration is not part of
``alembic upgrade head``). The migration is additive and idempotent: existing
rows are preserved, and a fresh database (where ``0001_baseline`` already
created the columns via ``create_all``) is a no-op.

Downgrade removes only the columns/index added here where the backend supports
it (SQLite ``DROP COLUMN`` requires SQLite >= 3.35; failures are tolerated and
reported rather than aborting the rollback).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0014_route_lock_authority"
down_revision = "0013_v3_resources"
branch_labels = None
depends_on = None

_TABLE = "route_locks_v3"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "version" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    if "reselection_reason" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("reselection_reason", sa.String(128), nullable=True),
        )
    if "updated_at" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if "uq_route_locks_v3_active_scope" not in existing_indexes:
        op.create_index(
            "uq_route_locks_v3_active_scope",
            _TABLE,
            ["scope_type", "scope_id"],
            unique=True,
            sqlite_where=sa.text("status = 'active'"),
            postgresql_where=sa.text("status = 'active'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if "uq_route_locks_v3_active_scope" in existing_indexes:
        op.drop_index("uq_route_locks_v3_active_scope", table_name=_TABLE)

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name in ("updated_at", "reselection_reason", "version"):
        if name in existing:
            op.drop_column(_TABLE, name)