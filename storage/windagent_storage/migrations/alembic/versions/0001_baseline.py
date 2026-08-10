"""0001 baseline — full canonical schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-03

Phase 1 — G1.1. The baseline builds the entire canonical schema from
``BaseORM.metadata`` (V2 canonical + V2 orchestration + V3 provider routing
tables). It is deliberately idempotent (``create_all`` with ``checkfirst``) so
it is safe to run on an existing database that was previously created with the
legacy ``create_tables`` flow; the migration then records the Alembic stamp.
"""

from __future__ import annotations

from alembic import op
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401  (registers tables)
import windagent_storage.orm.v3_models  # noqa: F401  (registers tables)
import windagent_storage.video_production.video_production_models  # noqa: F401  (registers V2 video production tables)

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every canonical table that does not already exist."""
    bind = op.get_bind()
    BaseORM.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop every canonical table managed by BaseORM.metadata."""
    bind = op.get_bind()
    BaseORM.metadata.drop_all(bind=bind)
    # Note: Alembic manages its own ``alembic_version`` stamp table after the
    # last downgrade script runs — we must not drop it here.
