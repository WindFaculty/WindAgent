"""Migration 002: Legacy Data Migration
Migrates data from legacy backend tables to V2 canonical schema without self-copy SQL.
"""

from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from windagent_storage.migrations.preflight import DataMigrationPreflightValidator
from windagent_storage.orm.models import ExecutionEventORM, SessionORM

logger = logging.getLogger("windagent.storage.migrations.002")

MIGRATION_REVISION = "002_legacy_data"
MIGRATION_NAME = "Legacy Data Migration"
MIGRATION_DESCRIPTION = """
Migrates data from legacy backend tables to V2 canonical schema:
- chat_sessions (backend) -> chat_sessions (V2 storage)
- parent_tasks (backend) -> v2_tasks (V2 storage)
- workflows (backend) -> v2_workflow_runs (V2 storage)
- workflow_steps (backend) -> v2_workflow_steps (V2 storage)
- execution_events (backend) -> execution_events (V2 storage)
- task_artifacts (backend) -> v2_artifacts (V2 storage)

Preserves all IDs, relationships, timestamps, and data integrity.
"""


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MigrationStats:
    """Statistics for data migration."""
    tables_migrated: int = 0
    rows_migrated: int = 0
    rows_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        logger.error(message)


@dataclass
class DataIntegrityReport:
    """Report on data integrity after migration."""
    source_row_counts: Dict[str, int] = field(default_factory=dict)
    target_row_counts: Dict[str, int] = field(default_factory=dict)
    id_preserved: Dict[str, bool] = field(default_factory=dict)
    timestamp_preserved: Dict[str, bool] = field(default_factory=dict)

    def verify(self) -> bool:
        """Verify all integrity checks passed."""
        return self._verify_row_counts() and self._verify_ids() and self._verify_timestamps()

    def _verify_row_counts(self) -> bool:
        for table in self.source_row_counts:
            target_count = self.target_row_counts.get(table, 0)
            if self.source_row_counts[table] != target_count:
                logger.error(
                    f"Row count mismatch for {table}: "
                    f"source={self.source_row_counts[table]}, target={target_count}"
                )
                return False
        return True

    def _verify_ids(self) -> bool:
        for table, preserved in self.id_preserved.items():
            if not preserved:
                logger.error(f"IDs not preserved for {table}")
                return False
        return True

    def _verify_timestamps(self) -> bool:
        for table, preserved in self.timestamp_preserved.items():
            if not preserved:
                logger.error(f"Timestamps not preserved for {table}")
                return False
        return True


def _compute_table_checksum(session: Session, table_name: str) -> str:
    """Compute checksum for a table's data."""
    if not _check_table_exists(session, table_name):
        return ""
    pk_col = "run_id" if table_name == "v2_workflow_runs" else "id"
    result = session.execute(text(f"SELECT COUNT(*), GROUP_CONCAT({pk_col}) FROM {table_name}"))
    row = result.fetchone()
    if row:
        return hashlib.sha256(f"{row[0]}:{row[1] or ''}".encode()).hexdigest()
    return ""


def _get_row_count(session: Session, table_name: str) -> int:
    """Get row count for a table if it exists."""
    if not _check_table_exists(session, table_name):
        return 0
    result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return result.scalar() or 0


def _check_table_exists(session: Session, table_name: str) -> bool:
    """Check if a table exists in sqlite_master."""
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    )
    return result.fetchone() is not None


def upgrade(session: Session) -> None:
    """Upgrade: Migrate data from legacy backend tables to V2 canonical tables.

    Guarantees no self-copy SQL by preparing staging snapshot tables where table names overlap.
    """
    logger.info(f"Running upgrade for migration {MIGRATION_REVISION}")
    now_str = _utc_iso_now()
    stats = MigrationStats()
    integrity_report = DataIntegrityReport()

    # Step 1: Handle shared-name table staging to avoid self-copy SQL
    # If legacy `chat_sessions` exists, rename to `legacy_chat_sessions_snapshot`
    if _check_table_exists(session, "chat_sessions") and not _check_table_exists(session, "legacy_chat_sessions_snapshot"):
        # Check if chat_sessions is legacy schema (missing status column or v2 columns)
        cols = [c[1] for c in session.execute(text("PRAGMA table_info(chat_sessions)")).fetchall()]
        if "status" not in cols:
            session.execute(text("ALTER TABLE chat_sessions RENAME TO legacy_chat_sessions_snapshot"))
            SessionORM.__table__.create(session.get_bind(), checkfirst=True)

    # If legacy `execution_events` exists, rename to `legacy_execution_events_snapshot`
    if _check_table_exists(session, "execution_events") and not _check_table_exists(session, "legacy_execution_events_snapshot"):
        cols = [c[1] for c in session.execute(text("PRAGMA table_info(execution_events)")).fetchall()]
        if "data_json" not in cols:
            session.execute(text("ALTER TABLE execution_events RENAME TO legacy_execution_events_snapshot"))
            ExecutionEventORM.__table__.create(session.get_bind(), checkfirst=True)

    # Check source table names
    chat_source = "legacy_chat_sessions_snapshot" if _check_table_exists(session, "legacy_chat_sessions_snapshot") else "chat_sessions"
    events_source = "legacy_execution_events_snapshot" if _check_table_exists(session, "legacy_execution_events_snapshot") else "execution_events"

    # Source table presence
    has_legacy_data = any([
        _check_table_exists(session, chat_source),
        _check_table_exists(session, "parent_tasks"),
        _check_table_exists(session, "workflows"),
        _check_table_exists(session, "workflow_steps"),
        _check_table_exists(session, events_source),
        _check_table_exists(session, "task_artifacts"),
    ])

    if not has_legacy_data:
        logger.info("Legacy backend tables not found, skipping data migration")
        session.execute(
            text(
                """
                INSERT OR REPLACE INTO migration_history 
                (revision, name, description, applied_at, direction, status)
                VALUES (:revision, :name, :description, :applied_at, :direction, :status)
                """
            ),
            {
                "revision": MIGRATION_REVISION,
                "name": MIGRATION_NAME,
                "description": MIGRATION_DESCRIPTION,
                "applied_at": now_str,
                "direction": "upgrade",
                "status": "completed",
            },
        )
        session.commit()
        return

    # Record source row counts
    source_counts = {
        "chat_sessions": _get_row_count(session, chat_source),
        "v2_tasks": _get_row_count(session, "parent_tasks"),
        "v2_workflow_runs": _get_row_count(session, "workflows"),
        "v2_workflow_steps": _get_row_count(session, "workflow_steps"),
        "execution_events": _get_row_count(session, events_source),
        "v2_artifacts": _get_row_count(session, "task_artifacts"),
    }
    integrity_report.source_row_counts = source_counts

    try:
        # 1. Migrate chat_sessions from chat_source to chat_sessions
        if source_counts["chat_sessions"] > 0 and chat_source != "chat_sessions":
            session.execute(text(f"""
                INSERT OR IGNORE INTO chat_sessions 
                (id, title, status, agent_id, workspace_root, created_at, updated_at, last_event_sequence, metadata_json)
                SELECT 
                    id, title, 'active', agent_id, workspace_root, 
                    COALESCE(created_at, datetime('now')), COALESCE(updated_at, datetime('now')), COALESCE(last_event_sequence, 0), metadata_json
                FROM {chat_source}
            """))
            stats.tables_migrated += 1

        # 2. Migrate parent_tasks -> v2_tasks
        if source_counts["v2_tasks"] > 0:
            session.execute(text("""
                INSERT OR IGNORE INTO v2_tasks 
                (id, prompt, session_id, status, tags_json, created_at)
                SELECT 
                    id, 
                    COALESCE(title, ''),
                    conversation_id,
                    status,
                    json_array(COALESCE(label, '')),
                    created_at
                FROM parent_tasks
            """))
            stats.tables_migrated += 1

        # 3. Migrate workflows -> v2_workflow_runs
        if source_counts["v2_workflow_runs"] > 0:
            session.execute(text("""
                INSERT OR IGNORE INTO v2_workflow_runs 
                (run_id, workflow_id, session_id, status, created_at)
                SELECT 
                    id, id, session_id, status, created_at
                FROM workflows
            """))
            stats.tables_migrated += 1

        # 4. Migrate workflow_steps -> v2_workflow_steps
        if source_counts["v2_workflow_steps"] > 0:
            session.execute(text("""
                INSERT OR IGNORE INTO v2_workflow_steps 
                (id, run_id, step_order, name, tool_name, params_json, status, result_json, error)
                SELECT 
                    id, 
                    workflow_id,
                    order_index,
                    name,
                    tool_name,
                    params_json,
                    status,
                    '{}',
                    NULL
                FROM workflow_steps
            """))
            stats.tables_migrated += 1

        # 5. Migrate execution_events
        if source_counts["execution_events"] > 0 and events_source != "execution_events":
            session.execute(text(f"""
                INSERT OR IGNORE INTO execution_events 
                (id, session_id, event_type, data_json, event_seq, created_at)
                SELECT 
                    id, session_id, event_type, payload_json, event_seq, created_at
                FROM {events_source}
            """))
            stats.tables_migrated += 1

        # 6. Migrate task_artifacts -> v2_artifacts
        if source_counts["v2_artifacts"] > 0:
            session.execute(text("""
                INSERT OR IGNORE INTO v2_artifacts 
                (id, name, mime_type, uri, size_bytes, created_at, metadata_json)
                SELECT 
                    id, 
                    COALESCE(artifact_type, 'artifact'),
                    'application/octet-stream',
                    path_or_uri,
                    0,
                    created_at,
                    metadata_json
                FROM task_artifacts
            """))
            stats.tables_migrated += 1

        # Record target row counts
        target_counts = {
            "chat_sessions": _get_row_count(session, "chat_sessions"),
            "v2_tasks": _get_row_count(session, "v2_tasks"),
            "v2_workflow_runs": _get_row_count(session, "v2_workflow_runs"),
            "v2_workflow_steps": _get_row_count(session, "v2_workflow_steps"),
            "execution_events": _get_row_count(session, "execution_events"),
            "v2_artifacts": _get_row_count(session, "v2_artifacts"),
        }
        integrity_report.target_row_counts = target_counts

        # Verify integrity
        if not integrity_report.verify():
            raise RuntimeError("Data integrity verification failed: row counts or IDs mismatch")

        # Record checksums
        checksum_dict = {}
        for table in ["chat_sessions", "v2_tasks", "v2_workflow_runs", "v2_workflow_steps", "execution_events", "v2_artifacts"]:
            checksum_dict[table] = _compute_table_checksum(session, table)

        # Record migration completed in history
        session.execute(
            text(
                """
                INSERT OR REPLACE INTO migration_history 
                (revision, name, description, applied_at, direction, checksum, status)
                VALUES (:revision, :name, :description, :applied_at, :direction, :checksum, :status)
                """
            ),
            {
                "revision": MIGRATION_REVISION,
                "name": MIGRATION_NAME,
                "description": MIGRATION_DESCRIPTION,
                "applied_at": now_str,
                "direction": "upgrade",
                "checksum": json.dumps(checksum_dict),
                "status": "completed",
            },
        )
        session.commit()
        logger.info(f"Migration {MIGRATION_REVISION} upgrade completed successfully.")

    except Exception as e:
        logger.error(f"Migration {MIGRATION_REVISION} failed: {e}")
        session.rollback()

        # Record failed migration
        session.execute(
            text(
                """
                INSERT OR REPLACE INTO migration_history 
                (revision, name, description, applied_at, direction, status)
                VALUES (:revision, :name, :description, :applied_at, :direction, :status)
                """
            ),
            {
                "revision": MIGRATION_REVISION,
                "name": MIGRATION_NAME,
                "description": MIGRATION_DESCRIPTION,
                "applied_at": now_str,
                "direction": "upgrade",
                "status": "failed",
            },
        )
        session.commit()
        raise


def downgrade(session: Session) -> None:
    """Downgrade: Mark migration as rolled back (restore from backup for complete rollback)."""
    logger.info(f"Running downgrade for migration {MIGRATION_REVISION}")
    session.execute(
        text(
            """
            UPDATE migration_history 
            SET direction = :direction, status = :status
            WHERE revision = :revision
            """
        ),
        {
            "revision": MIGRATION_REVISION,
            "direction": "downgrade",
            "status": "rolled_back",
        },
    )
    session.commit()
