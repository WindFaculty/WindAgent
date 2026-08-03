"""0002 legacy → V2 data conversion

Revision ID: 0002_legacy_v2_data
Revises: 0001_baseline
Create Date: 2026-08-03

Phase 1 — G1.1. Converts the legacy backend tables into the canonical V2
schema, preserving every needed value (ids, titles, statuses, timestamps,
metadata, objective):

- ``chat_sessions``/``execution_events`` (legacy shape) are staged as
  ``legacy_*_snapshot`` and their rows inserted into the canonical tables.
- ``parent_tasks``  -> ``v2_tasks``
- ``workflows``     -> ``v2_workflow_runs``
- ``workflow_steps``-> ``v2_workflow_steps``
- ``task_artifacts``-> ``v2_artifacts``

This is a transaction-managed rewrite of the pre-Alembic
``migration_002_legacy_data``; Alembic owns the transaction so the migration
never issues its own ``commit()``.

Dialect note: SQLite rejects ``INSERT ... SELECT ... FROM ... ON CONFLICT``
(upsert clause after a SELECT-with-FROM), so the upsert is composed per dialect:
``INSERT OR IGNORE`` on SQLite, ``ON CONFLICT DO NOTHING`` on PostgreSQL.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_legacy_v2_data"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    """Live DDL check — never uses the (possibly stale) cached Inspector."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(
            bind.execute(
                sa.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
            ).scalar()
        )
    row = bind.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
        ),
        {"name": name},
    ).fetchone()
    return row is not None


def _columns(name: str) -> list[str]:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        rows = bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns WHERE table_name=:name"
            ),
            {"name": name},
        ).fetchall()
        return [r[0] for r in rows]
    rows = bind.execute(sa.text(f"PRAGMA table_info({name})")).fetchall()
    return [r[1] for r in rows]


def _count(name: str) -> int:
    bind = op.get_bind()
    return bind.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0


def _insert_select(select_sql: str, expected: int) -> None:
    """Execute an ``INSERT INTO t (...) SELECT ...`` idempotently per dialect.

    ``select_sql`` is the plain INSERT...SELECT statement without a conflict
    clause. SQLite gets ``INSERT OR IGNORE`` (its INSERT...SELECT...FROM form
    does not accept a trailing ``ON CONFLICT``); PostgreSQL gets the standard
    ``ON CONFLICT DO NOTHING`` suffix.

    The affected-row count must equal ``expected`` (the source row count): a
    shorter count means rows were silently skipped by the conflict clause and
    the migration fails loudly instead of losing data (Phase 1 exit gate:
    "không mất dữ liệu cần giữ").
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        result = bind.execute(sa.text(select_sql + " ON CONFLICT DO NOTHING"))
    else:
        result = bind.execute(sa.text(select_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)))
    inserted = result.rowcount if result is not None else 0
    if inserted != expected:
        raise RuntimeError(
            f"Migration 0002 data lane expected {expected} rows but inserted "
            f"{inserted} — rows were skipped by the upsert; refusing to proceed "
            "to avoid silent data loss."
        )


def upgrade() -> None:
    # 1. Stage legacy same-name tables when their shape differs from canonical.
    if _table_exists("chat_sessions") and "status" not in _columns("chat_sessions"):
        op.execute("ALTER TABLE chat_sessions RENAME TO legacy_chat_sessions_snapshot")
    if _table_exists("execution_events") and "data_json" not in _columns("execution_events"):
        op.execute("ALTER TABLE execution_events RENAME TO legacy_execution_events_snapshot")

    chat_source = "legacy_chat_sessions_snapshot" if _table_exists("legacy_chat_sessions_snapshot") else "chat_sessions"
    events_source = "legacy_execution_events_snapshot" if _table_exists("legacy_execution_events_snapshot") else "execution_events"

    has_legacy = any(
        _table_exists(t)
        for t in (
            chat_source,
            "parent_tasks",
            "workflows",
            "workflow_steps",
            events_source,
            "task_artifacts",
        )
    )
    if not has_legacy:
        return

    # 2. chat_sessions (legacy shape) -> canonical chat_sessions.
    if chat_source != "chat_sessions" and _count(chat_source) > 0:
        _insert_select(
            f"""
            INSERT INTO chat_sessions
            (id, title, status, agent_id, workspace_root, created_at, updated_at, last_event_sequence, metadata_json)
            SELECT
                id, title, 'active', agent_id, workspace_root,
                COALESCE(created_at, CURRENT_TIMESTAMP), COALESCE(updated_at, CURRENT_TIMESTAMP),
                COALESCE(last_event_sequence, 0), metadata_json
            FROM {chat_source}
            """,
            _count(chat_source),
        )

    # 3. parent_tasks -> v2_tasks.
    if _table_exists("parent_tasks") and _count("parent_tasks") > 0:
        _insert_select(
            """
            INSERT INTO v2_tasks
            (id, prompt, session_id, status, tags_json, created_at)
            SELECT
                id,
                COALESCE(title, ''),
                conversation_id,
                COALESCE(status, 'pending'),
                '["' || COALESCE(label, '') || '"]',
                COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM parent_tasks
            """,
            _count("parent_tasks"),
        )

    # 4. workflows -> v2_workflow_runs.
    if _table_exists("workflows") and _count("workflows") > 0:
        _insert_select(
            """
            INSERT INTO v2_workflow_runs
            (run_id, workflow_id, session_id, status, created_at)
            SELECT id, id, session_id, COALESCE(status, 'pending'),
                   COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM workflows
            """,
            _count("workflows"),
        )

    # 5. workflow_steps -> v2_workflow_steps.
    if _table_exists("workflow_steps") and _count("workflow_steps") > 0:
        _insert_select(
            """
            INSERT INTO v2_workflow_steps
            (id, run_id, step_order, name, tool_name, params_json, status, result_json, error)
            SELECT
                id,
                workflow_id,
                COALESCE(order_index, 0),
                COALESCE(name, ''),
                COALESCE(tool_name, ''),
                COALESCE(params_json, '{}'),
                COALESCE(status, 'pending'),
                '{}',
                NULL
            FROM workflow_steps
            """,
            _count("workflow_steps"),
        )

    # 6. execution_events (legacy shape) -> canonical execution_events.
    if events_source != "execution_events" and _count(events_source) > 0:
        _insert_select(
            f"""
            INSERT INTO execution_events
            (id, session_id, event_type, data_json, event_seq, created_at)
            SELECT
                id, session_id, event_type, payload_json, COALESCE(event_seq, 0), created_at
            FROM {events_source}
            """,
            _count(events_source),
        )

    # 7. task_artifacts -> v2_artifacts.
    if _table_exists("task_artifacts") and _count("task_artifacts") > 0:
        _insert_select(
            """
            INSERT INTO v2_artifacts
            (id, name, mime_type, uri, size_bytes, created_at, metadata_json)
            SELECT
                id,
                COALESCE(artifact_type, 'artifact'),
                'application/octet-stream',
                path_or_uri,
                0,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(metadata_json, '{}')
            FROM task_artifacts
            """,
            _count("task_artifacts"),
        )


def downgrade() -> None:
    """Data migration downgrade is intentionally a no-op.

    Rows copied into canonical V2 tables are append-only audit/migrated data
    and are never deleted by a schema downgrade (Phase 9 rollback policy: the
    application DB is restored from a pre-migration backup instead).
    """
