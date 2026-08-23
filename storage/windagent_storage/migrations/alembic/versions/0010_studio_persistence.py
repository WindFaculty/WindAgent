"""0010 studio persistence — additive Studio schema + deterministic backfill

Revision ID: 0010_studio_persistence
Revises: 0009_immutable_plan_revisions
Create Date: 2026-08-10

Plan A — A3 (studio.contract/v0.1). One ordered additive migration:

1. Create the eight Studio tables (series, episodes, revisions, artifacts,
   approval policies/decisions, runs, events) plus their uniqueness indexes:
   - one episode number per series,
   - one revision content hash per episode,
   - one artifact content hash globally,
   - one approval decision per (revision, checkpoint, actor),
   - one event sequence per aggregate.
2. Extend the existing outbox (``v2_outbox_records``) for Studio events with
   per-aggregate ordering: a partial unique index on (aggregate_id,
   sequence_number) is added only when existing rows do not already violate it
   (guard: never block an upgrade over legacy data).
3. Backfill legacy ``video_production_projects`` /
   ``video_production_revisions`` rows deterministically into Studio tables.
   Backfill is structural only — no story content is invented. Each legacy
   project becomes one SeriesProject (same id VALUE, so no second project
   row) plus one placeholder Episode; each legacy revision becomes a
   Studio revision bound to that episode.

The migration is reversible: downgrade drops Studio tables and the outbox
index; legacy V2 tables and rows are untouched. ``if_not_exists`` makes the
upgrade safe on databases where a previous metadata ``create_all`` already
materialized Studio tables.
"""

from __future__ import annotations

import json
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

from windagent_storage.studio.backfill import (
    episode_metadata,
    map_legacy_status,
    normalize_legacy_hash,
    revision_metadata,
    series_metadata,
    synthetic_episode_id,
    lock_state_for,
)

logger = logging.getLogger("windagent.storage.migrations")

# revision identifiers, used by Alembic.
revision = "0010_studio_persistence"
down_revision = "0009_immutable_plan_revisions"
branch_labels = None
depends_on = None


def _create_studio_tables() -> None:
    op.create_table(
        "studio_series_projects",
        sa.Column("series_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("episode_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        if_not_exists=True,
    )
    op.create_table(
        "studio_episodes",
        sa.Column("episode_id", sa.String(64), primary_key=True),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("current_revision_id", sa.String(64), nullable=True),
        sa.Column("active_run_id", sa.String(64), nullable=True),
        sa.Column("awaiting_checkpoint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        if_not_exists=True,
    )
    op.create_table(
        "studio_revisions",
        sa.Column("revision_id", sa.String(64), primary_key=True),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("episode_id", sa.String(64), nullable=False),
        sa.Column("parent_revision_id", sa.String(64), nullable=True),
        sa.Column("creator", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("lock_state", sa.String(32), nullable=False, server_default="UNLOCKED"),
        sa.Column("invalidation_intent", sa.String(32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="0"),
        if_not_exists=True,
    )
    op.create_table(
        "studio_artifacts",
        sa.Column("artifact_id", sa.String(64), primary_key=True),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False, server_default="studio.artifact/v1alpha1"),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("episode_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_artifact_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("prompt_id", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("model_route_id", sa.String(64), nullable=True),
        sa.Column("provider_id", sa.String(64), nullable=True),
        sa.Column("model_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="system"),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        if_not_exists=True,
    )
    op.create_table(
        "studio_approval_policies",
        sa.Column("policy_id", sa.String(64), primary_key=True),
        sa.Column("policy_version", sa.String(64), primary_key=True),
        sa.Column("checkpoint_to_mode_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quality_thresholds_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("max_review_revision_iterations", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("required_approver_roles_json", sa.Text(), nullable=False, server_default='["OWNER"]'),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "studio_approval_decisions",
        sa.Column("approval_id", sa.String(64), primary_key=True),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="OWNER"),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "studio_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("episode_id", sa.String(64), nullable=False),
        sa.Column("dag_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        if_not_exists=True,
    )
    op.create_table(
        "studio_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False, server_default="studio.event/v1"),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False, server_default="studio"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("causation_id", sa.String(64), nullable=True),
        sa.Column("studio_run_id", sa.String(64), nullable=True),
        sa.Column("revision_ref", sa.String(64), nullable=True),
        sa.Column("artifact_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        if_not_exists=True,
    )


def _create_unique_indexes() -> None:
    op.create_index(
        "uq_studio_episode_series_number",
        "studio_episodes",
        ["series_id", "episode_number"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_studio_revision_episode_hash",
        "studio_revisions",
        ["episode_id", "content_hash"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_studio_artifact_hash",
        "studio_artifacts",
        ["content_hash"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_studio_approval_revision_checkpoint_actor",
        "studio_approval_decisions",
        ["revision_id", "checkpoint", "actor"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "uq_studio_event_aggregate_sequence",
        "studio_events",
        ["aggregate_id", "sequence"],
        unique=True,
        if_not_exists=True,
    )


def _extend_outbox_for_studio() -> None:
    """Add per-aggregate ordering to the existing outbox, guarded against legacy duplicates."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("v2_outbox_records")}
    if "uq_v2_outbox_aggregate_sequence" in indexes:
        return
    duplicates = bind.execute(
        text(
            "SELECT aggregate_id, sequence_number, COUNT(*) AS n "
            "FROM v2_outbox_records WHERE aggregate_id IS NOT NULL "
            "GROUP BY aggregate_id, sequence_number HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates is not None:
        logger.warning(
            "Skip uq_v2_outbox_aggregate_sequence: legacy outbox rows already "
            "violate (aggregate_id=%s, sequence=%s); Studio ordering enforced by the UoW writer.",
            duplicates[0],
            duplicates[1],
        )
        return
    op.create_index(
        "uq_v2_outbox_aggregate_sequence",
        "v2_outbox_records",
        ["aggregate_id", "sequence_number"],
        unique=True,
        sqlite_where=text("aggregate_id IS NOT NULL"),
        postgresql_where=text("aggregate_id IS NOT NULL"),
    )


def _backfill_legacy_data() -> None:
    """Deterministic structural backfill of V2 projects/revisions (never story content)."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "video_production_projects" not in tables:
        return
    if not inspector.get_columns("video_production_projects"):
        return

    projects = bind.execute(
        text(
            "SELECT id, name, status, active_revision_id, created_at, updated_at "
            "FROM video_production_projects"
        )
    ).fetchall()
    for row in projects:
        project_id, name, status, active_revision_id, created_at, updated_at = row
        series_sql = (
            "INSERT INTO studio_series_projects "
            "(series_id, title, description, episode_ids_json, created_at, updated_at, metadata_json) "
            "VALUES (:sid, :title, '', :episodes, :created_at, :updated_at, :meta) "
            "ON CONFLICT(series_id) DO NOTHING"
            if bind.dialect.name == "postgresql"
            else "INSERT OR IGNORE INTO studio_series_projects "
            "(series_id, title, description, episode_ids_json, created_at, updated_at, metadata_json) "
            "VALUES (:sid, :title, '', :episodes, :created_at, :updated_at, :meta)"
        )
        bind.execute(text(series_sql),
            {
                "sid": project_id,
                "title": name or "Untitled Production",
                "episodes": json.dumps([synthetic_episode_id(project_id)]),
                "created_at": created_at,
                "updated_at": updated_at,
                "meta": json.dumps(
                    series_metadata(
                        legacy_status=status or "ACTIVE",
                        legacy_active_revision_id=active_revision_id or "",
                    )
                ),
            },
        )
        episode_sql = (
            "INSERT INTO studio_episodes "
            "(episode_id, series_id, title, episode_number, state, created_at, updated_at, "
            "optimistic_version, metadata_json) "
            "VALUES (:eid, :sid, :title, 1, 'DRAFT', :created_at, :updated_at, 0, :meta) "
            "ON CONFLICT(episode_id) DO NOTHING"
            if bind.dialect.name == "postgresql"
            else "INSERT OR IGNORE INTO studio_episodes "
            "(episode_id, series_id, title, episode_number, state, created_at, updated_at, "
            "optimistic_version, metadata_json) "
            "VALUES (:eid, :sid, :title, 1, 'DRAFT', :created_at, :updated_at, 0, :meta)"
        )
        bind.execute(text(episode_sql),
            {
                "eid": synthetic_episode_id(project_id),
                "sid": project_id,
                "title": name or "Untitled Production",
                "created_at": created_at,
                "updated_at": updated_at,
                "meta": json.dumps(episode_metadata(legacy_project_id=project_id)),
            },
        )

    if "video_production_revisions" not in tables:
        return
    revisions = bind.execute(
        text(
            "SELECT id, project_id, parent_revision_id, status, content_hash, sequence, created_at "
            "FROM video_production_revisions"
        )
    ).fetchall()
    for row in revisions:
        rev_id, project_id, parent_id, status, content_hash, sequence, created_at = row
        hash_backfilled = not (content_hash and len(str(content_hash)) == 64)
        final_hash = normalize_legacy_hash(str(content_hash or ""), rev_id, sequence or 0, status or "DRAFT")
        mapped = map_legacy_status(status or "DRAFT")
        revision_sql = (
            "INSERT INTO studio_revisions "
            "(revision_id, series_id, episode_id, parent_revision_id, creator, actor, created_at, "
            "content_hash, state, status, lock_state, invalidation_intent, summary, metadata_json, "
            "optimistic_version) "
            "VALUES (:rid, :sid, :eid, :parent, 'legacy:migration', 'legacy:migration', :created_at, "
            ":hash, :state, :state, :lock_state, NULL, '', :meta, 0) "
            "ON CONFLICT(revision_id) DO NOTHING"
            if bind.dialect.name == "postgresql"
            else "INSERT OR IGNORE INTO studio_revisions "
            "(revision_id, series_id, episode_id, parent_revision_id, creator, actor, created_at, "
            "content_hash, state, status, lock_state, invalidation_intent, summary, metadata_json, "
            "optimistic_version) "
            "VALUES (:rid, :sid, :eid, :parent, 'legacy:migration', 'legacy:migration', :created_at, "
            ":hash, :state, :state, :lock_state, NULL, '', :meta, 0)"
        )
        bind.execute(text(revision_sql),
            {
                "rid": rev_id,
                "sid": project_id,
                "eid": synthetic_episode_id(project_id),
                "parent": parent_id,
                "created_at": created_at,
                "hash": final_hash,
                "state": mapped,
                "lock_state": lock_state_for(status or "DRAFT", mapped),
                "meta": json.dumps(
                    revision_metadata(
                        legacy_status=status or "DRAFT",
                        legacy_sequence=sequence or 0,
                        hash_backfilled=hash_backfilled,
                    )
                ),
            },
        )


def upgrade() -> None:
    _create_studio_tables()
    _create_unique_indexes()
    _extend_outbox_for_studio()
    _backfill_legacy_data()


def downgrade() -> None:
    for index in [
        "uq_studio_event_aggregate_sequence",
        "uq_studio_approval_revision_checkpoint_actor",
        "uq_studio_artifact_hash",
        "uq_studio_revision_episode_hash",
        "uq_studio_episode_series_number",
        "uq_v2_outbox_aggregate_sequence",
    ]:
        op.drop_index(index, table_name=None, if_exists=True)
    for table in [
        "studio_events",
        "studio_runs",
        "studio_approval_decisions",
        "studio_approval_policies",
        "studio_artifacts",
        "studio_revisions",
        "studio_episodes",
        "studio_series_projects",
    ]:
        op.drop_table(table, if_exists=True)
