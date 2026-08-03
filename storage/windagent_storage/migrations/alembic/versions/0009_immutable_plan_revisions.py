"""0009 immutable plan revisions

Revision ID: 0009_immutable_plan_revisions
Revises: 0008_conversation_stream_recovery
Create Date: 2026-08-03

Enforce a single immutable version number per parent task.  The application
uses the active-plan pointer as a compare-and-swap precondition, while this
constraint protects the append-only history from duplicate version numbers.
"""

from __future__ import annotations

from alembic import op


revision = "0009_immutable_plan_revisions"
down_revision = "0008_conversation_stream_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_plan_versions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_task_plan_versions_parent_version",
            ["parent_task_id", "version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("task_plan_versions") as batch_op:
        batch_op.drop_constraint(
            "uq_task_plan_versions_parent_version",
            type_="unique",
        )
