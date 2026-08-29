"""0031 Organizational Learning and Multi-Agent Knowledge Sharing (Phase 14) - ban_ke_hoach_v1 §20, §23, §24, §25."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0031_organizational_learning"
down_revision = "0030_subagent_evolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "learned_rules" not in existing:
        op.create_table(
            "learned_rules",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("condition", sa.Text(), nullable=False),
            sa.Column("recommendation", sa.Text(), nullable=False),
            sa.Column("domain", sa.String(64), nullable=False, server_default="general"),
            sa.Column("scope", sa.String(32), nullable=False, server_default="project"),
            sa.Column("target_role", sa.String(64), nullable=True),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("harness_version", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("state", sa.String(32), nullable=False, server_default="candidate"),
            sa.Column("supersedes_id", sa.String(64), nullable=True),
            sa.Column("superseded_by", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index("ix_learned_rules_domain", "learned_rules", ["domain"])
        op.create_index("ix_learned_rules_state", "learned_rules", ["state"])
        op.create_index("ix_rule_domain_state", "learned_rules", ["domain", "state"])
        op.create_index("ix_rule_created_at", "learned_rules", ["created_at"])
        op.create_index("ix_learned_rules_role_state", "learned_rules", ["target_role", "state"])
        op.create_index("ix_learned_rules_project_state", "learned_rules", ["project_id", "state"])
    else:
        existing_cols = {c["name"] for c in inspector.get_columns("learned_rules")}
        if "target_role" not in existing_cols:
            op.add_column("learned_rules", sa.Column("target_role", sa.String(64), nullable=True))
        if "project_id" not in existing_cols:
            op.add_column("learned_rules", sa.Column("project_id", sa.String(64), nullable=True))
        if "activated_at" not in existing_cols:
            op.add_column("learned_rules", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
        if "deprecated_at" not in existing_cols:
            op.add_column("learned_rules", sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True))
        if "supersedes_id" not in existing_cols:
            op.add_column("learned_rules", sa.Column("supersedes_id", sa.String(64), nullable=True))
        if "superseded_by" not in existing_cols:
            op.add_column("learned_rules", sa.Column("superseded_by", sa.String(64), nullable=True))
        if "metadata_json" not in existing_cols:
            op.add_column("learned_rules", sa.Column("metadata_json", sa.Text(), nullable=True, server_default="{}"))

        existing_indexes = {ix["name"] for ix in inspector.get_indexes("learned_rules")}
        if "ix_learned_rules_role_state" not in existing_indexes:
            op.create_index("ix_learned_rules_role_state", "learned_rules", ["target_role", "state"])
        if "ix_learned_rules_project_state" not in existing_indexes:
            op.create_index("ix_learned_rules_project_state", "learned_rules", ["project_id", "state"])

    if "conflict_resolutions" not in existing:
        op.create_table(
            "conflict_resolutions",
            sa.Column("resolution_id", sa.String(64), primary_key=True),
            sa.Column("domain", sa.String(64), nullable=False),
            sa.Column("context_query_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("winning_rule_id", sa.String(64), nullable=False),
            sa.Column("competing_rule_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("resolution_rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("score_breakdown_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_conflict_res_domain", "conflict_resolutions", ["domain"])
        op.create_index("ix_conflict_res_resolved_at", "conflict_resolutions", ["resolved_at"])

    if "multi_agent_attributions" not in existing:
        op.create_table(
            "multi_agent_attributions",
            sa.Column("attribution_id", sa.String(64), primary_key=True),
            sa.Column("episode_id", sa.String(64), nullable=False),
            sa.Column("domain", sa.String(64), nullable=False, server_default="youtube_studio"),
            sa.Column("metric_signals_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("role_attributions_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_attributions_episode_id", "multi_agent_attributions", ["episode_id"])
        op.create_index("ix_attributions_created_at", "multi_agent_attributions", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "multi_agent_attributions" in existing:
        op.drop_table("multi_agent_attributions")
    if "conflict_resolutions" in existing:
        op.drop_table("conflict_resolutions")

    if "learned_rules" in existing:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("learned_rules")}
        for ix_name in [
            "ix_learned_rules_project_state",
            "ix_learned_rules_role_state",
            "ix_learned_rules_project_id",
            "ix_learned_rules_target_role",
            "ix_learned_rules_scope",
        ]:
            if ix_name in existing_indexes:
                op.drop_index(ix_name, table_name="learned_rules")

        with op.batch_alter_table("learned_rules") as batch_op:
            existing_cols = {c["name"] for c in inspector.get_columns("learned_rules")}
            for col in ["target_role", "project_id", "activated_at", "deprecated_at", "supersedes_id", "superseded_by", "metadata_json"]:
                if col in existing_cols:
                    batch_op.drop_column(col)
