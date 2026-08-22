"""0016 binding discovery metadata + truthful pricing (P0.2).

Revision ID: 0016_binding_discovery_metadata
Revises: 0015_execution_lease_release
Create Date: 2026-08-22

Adds the P0.2 model-catalog columns to ``endpoint_model_bindings``:

- ``availability``       active | unavailable | deprecated (reconciliation;
                         a missed sync NEVER deletes a binding)
- ``pricing_class``      FREE | PAID | UNKNOWN (UNKNOWN until the provider
                         advertises pricing — never guessed)
- ``input_price``        provider-advertised USD/token (nullable)
- ``output_price``       provider-advertised USD/token (nullable)
- ``currency``           advertised currency, e.g. USD (nullable)
- ``last_discovered_at`` last successful discovery timestamp

Additive and idempotent: fresh databases created via ``create_all`` already
carry the columns; existing databases get them appended.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0016_binding_discovery_metadata"
down_revision = "0015_execution_lease_release"
branch_labels = None
depends_on = None

_TABLE = "endpoint_model_bindings"

_COLUMNS = {
    "availability": sa.Column("availability", sa.String(16), nullable=False,
                              server_default="active"),
    "pricing_class": sa.Column("pricing_class", sa.String(16), nullable=False,
                               server_default="UNKNOWN"),
    "input_price": sa.Column("input_price", sa.Float(), nullable=True),
    "output_price": sa.Column("output_price", sa.Float(), nullable=True),
    "currency": sa.Column("currency", sa.String(8), nullable=True),
    "last_discovered_at": sa.Column("last_discovered_at", sa.DateTime(), nullable=True),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column(_TABLE, column.copy())


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name in reversed(list(_COLUMNS.keys())):
        if name in existing:
            op.drop_column(_TABLE, name)
