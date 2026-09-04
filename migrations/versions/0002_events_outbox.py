"""Platform event store + transactional outbox (Phase 6).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02

Creates the platform-owned ``platform_events`` (append-only event store)
and ``platform_outbox`` (transactional outbox) tables.  Column definitions
live once in ``windagent.platform.events.outbox`` so the migration and the
runtime adapter can never drift apart.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from windagent.platform.events.outbox import events_table, outbox_table

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    events_table.create(bind=bind)
    outbox_table.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    outbox_table.drop(bind=bind)
    events_table.drop(bind=bind)
