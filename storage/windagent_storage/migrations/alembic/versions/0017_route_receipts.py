"""0017 route receipts (P0.3.6).

Revision ID: 0017_route_receipts
Revises: 0016_binding_discovery_metadata
Create Date: 2026-08-22

Creates ``model_route_receipts_v3`` — one durable receipt per LLM task
execution through the model router (P0.3.6):

- ``task_id``            durable studio task id (or provider request id)
- ``role``               canonical routing role / capability label
- ``rule_id``            id of the matched routing rule
- ``route_lock_id``      primary route lock (FK ``route_locks_v3.id``)
- ``selected_provider``  provider/vendor that served the completion
- ``selected_model_id``  canonical model that served the completion
- ``provider_model_id``  provider-native model id (nullable)
- ``endpoint_id``        endpoint that served the completion (nullable)
- ``fallback_used``      whether the rule-declared fallback model served it
- ``fallback_reason``    typed failure code that triggered the fallback
- ``status``             success | failed
- ``error_code``         typed failure code when status=failed
- ``started_at``/``completed_at``  wall-clock execution window

Additive and idempotent: fresh databases created via ``create_all`` already
carry the table; existing databases create it only when missing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0017_route_receipts"
down_revision = "0016_binding_discovery_metadata"
branch_labels = None
depends_on = None

_TABLE = "model_route_receipts_v3"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE in set(inspector.get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(128), nullable=False, server_default=""),
        sa.Column("rule_id", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "route_lock_id",
            sa.String(128),
            sa.ForeignKey("route_locks_v3.id"),
            nullable=False,
        ),
        sa.Column("selected_provider", sa.String(128), nullable=True),
        sa.Column("selected_model_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("provider_model_id", sa.String(128), nullable=True),
        sa.Column("endpoint_id", sa.String(128), nullable=True),
        sa.Column(
            "fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("fallback_reason", sa.String(128), nullable=True),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="success"
        ),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_model_route_receipts_task", _TABLE, ["task_id"]
    )
    op.create_index(
        "ix_model_route_receipts_role_created", _TABLE, ["role", "created_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    op.drop_table(_TABLE)
