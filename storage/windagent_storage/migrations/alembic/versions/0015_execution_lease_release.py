"""0015 persist execution lease release timestamp (Phase 5B1).

Revision ID: 0015_execution_lease_release
Revises: 0014_route_lock_authority
Create Date: 2026-08-20

Adds the nullable ``released_at`` column to ``execution_leases`` so the
transactional finalizer can persist when a lease was released/completed. The
migration is additive and idempotent: existing rows are preserved, and a fresh
database (where ``0001_baseline`` already created the column via
``create_all``) is a no-op.

Downgrade removes only the ``released_at`` column (SQLite ``DROP COLUMN``
requires SQLite >= 3.35).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0015_execution_lease_release"
down_revision = "0014_route_lock_authority"
branch_labels = None
depends_on = None

_TABLE = "execution_leases"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "released_at" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("released_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "released_at" in existing:
        op.drop_column(_TABLE, "released_at")