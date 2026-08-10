"""0011 studio run nodes — durable per-node DAG state (Plan A — A4)

Revision ID: 0011_studio_run_nodes
Revises: 0010_studio_persistence
Create Date: 2026-08-10

Plan A — A4 (studio.contract/v0.1). One ordered additive migration:

1. Create ``studio_run_nodes``: per-node state of a durable Studio story run.
   Node status drives the orchestrator: PENDING -> RUNNABLE -> DISPATCHED ->
   SUCCEEDED/FAILED/CANCELLED, with WAITING_APPROVAL as a durable approval-gate
   state. ``task_id`` carries the committed durable queue identity (set only
   after the queue insert committed), ``attempt`` the retry budget counter,
   ``version`` the optimistic-concurrency guard for stale writes.
2. Two supporting indexes: node status (reconciliation scans) and task_id
   (completion lookup by durable task identity).

The migration is reversible: downgrade drops the node table only; Studio runs,
legacy V2 rows, and the outbox are untouched. ``if_not_exists`` makes the
upgrade safe on databases where a previous metadata ``create_all`` already
materialized the table.
"""

from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("windagent.storage.migrations")

# revision identifiers, used by Alembic.
revision = "0011_studio_run_nodes"
down_revision = "0010_studio_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_run_nodes",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("dag_node_id", sa.String(64), primary_key=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("depends_on_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("checkpoint", sa.String(64), nullable=True),
        sa.Column("gate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_hashes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("output_hashes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("output_artifact_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_studio_run_nodes_status",
        "studio_run_nodes",
        ["status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_studio_run_nodes_task_id",
        "studio_run_nodes",
        ["task_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_studio_run_nodes_task_id", table_name="studio_run_nodes", if_exists=True)
    op.drop_index("ix_studio_run_nodes_status", table_name="studio_run_nodes", if_exists=True)
    op.drop_table("studio_run_nodes")
