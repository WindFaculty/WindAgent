"""0012 persist complete Studio provider provenance.

Revision ID: 0012_studio_artifact_provenance
Revises: 0011_studio_run_nodes
Create Date: 2026-08-11

Adds only redaction-safe identifiers needed to reconstruct a model-backed
Studio artifact's route, endpoint binding, provider attempt, and structured
output contract. No request/response content or credentials are stored here.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0012_studio_artifact_provenance"
down_revision = "0011_studio_run_nodes"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("canonical_model_id", 128),
    ("provider_model_id", 128),
    ("endpoint_id", 128),
    ("provider_binding_id", 128),
    ("provider_attempt_id", 128),
    ("provider_request_id", 128),
    ("output_schema_contract", 160),
)


def upgrade() -> None:
    existing = {
        column["name"]
        for column in inspect(op.get_bind()).get_columns("studio_artifacts")
    }
    for name, length in _COLUMNS:
        if name in existing:
            continue
        op.add_column(
            "studio_artifacts",
            sa.Column(name, sa.String(length), nullable=True),
        )


def downgrade() -> None:
    existing = {
        column["name"]
        for column in inspect(op.get_bind()).get_columns("studio_artifacts")
    }
    for name, _length in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("studio_artifacts", name)
