"""0025 Experience Store records (Phase 8) - ban_ke_hoach_v1 §13 & §24."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0025_experience_store"
down_revision = "0024_evaluation_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "experience_records" not in existing:
        op.create_table(
            "experience_records",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("execution_id", sa.String(64), nullable=False),
            sa.Column("trajectory_id", sa.String(64), nullable=True),
            sa.Column("parent_task_id", sa.String(64), nullable=True),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("state", sa.String(32), nullable=False, server_default="raw"),
            sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("decision_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("action_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("artifacts_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("evaluator_results_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("hypothesis", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_experience_records_execution_id", "experience_records", ["execution_id"])
        op.create_index("ix_experience_records_trajectory_id", "experience_records", ["trajectory_id"])
        op.create_index("ix_experience_records_parent_task_id", "experience_records", ["parent_task_id"])
        op.create_index("ix_experience_records_session_id", "experience_records", ["session_id"])
        op.create_index("ix_experience_records_project_id", "experience_records", ["project_id"])
        op.create_index("ix_experience_records_state", "experience_records", ["state"])
        op.create_index("ix_experience_records_confidence", "experience_records", ["confidence"])
        op.create_index("ix_experience_state_conf", "experience_records", ["state", "confidence"])
        op.create_index("ix_experience_proj_state", "experience_records", ["project_id", "state"])
        op.create_index("ix_experience_exec_state", "experience_records", ["execution_id", "state"])
        op.create_index("ix_experience_created_at", "experience_records", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "experience_records" in existing:
        op.drop_table("experience_records")

