"""0024 Evaluation Engine V2 records (Phase 7) - ban_ke_hoach_v1 §12."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0024_evaluation_v2"
down_revision = "0023_memory_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "evaluation_records" not in existing:
        op.create_table(
            "evaluation_records",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("execution_id", sa.String(64), nullable=False),
            sa.Column("trajectory_id", sa.String(64), nullable=False),
            sa.Column("evaluator_version", sa.String(32), nullable=False, server_default="2.0.0"),
            sa.Column("harness_version", sa.String(32), nullable=True),
            sa.Column("dimension", sa.String(32), nullable=False),
            sa.Column("metric_name", sa.String(64), nullable=False),
            sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("threshold", sa.Float(), nullable=False, server_default="0.7"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_evaluation_records_execution_id", "evaluation_records", ["execution_id"])
        op.create_index("ix_evaluation_records_trajectory_id", "evaluation_records", ["trajectory_id"])
        op.create_index("ix_evaluation_records_evaluator_ver", "evaluation_records", ["evaluator_version"])
        op.create_index("ix_evaluation_records_harness_ver", "evaluation_records", ["harness_version"])
        op.create_index("ix_evaluation_records_dimension", "evaluation_records", ["dimension"])
        op.create_index("ix_evaluation_records_metric_name", "evaluation_records", ["metric_name"])
        op.create_index("ix_evaluation_records_passed", "evaluation_records", ["passed"])
        op.create_index("ix_evaluation_records_blocked", "evaluation_records", ["blocked"])
        op.create_index("ix_evaluation_exec_metric", "evaluation_records", ["execution_id", "metric_name"])
        op.create_index("ix_evaluation_dim_score", "evaluation_records", ["dimension", "score"])
        op.create_index("ix_evaluation_harness_metric", "evaluation_records", ["harness_version", "metric_name"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "evaluation_records" in existing:
        op.drop_table("evaluation_records")

