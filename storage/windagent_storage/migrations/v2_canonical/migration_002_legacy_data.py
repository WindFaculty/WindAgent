"""
Migration 002: Legacy Data Migration
Migrates data from legacy backend tables to V2 canonical schema.
"""

from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

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


@dataclass
class MigrationStats:
    """Statistics for data migration."""
    tables_migrated: int = 0
    rows_migrated: int = 0
    rows_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)
    
    def add_error(self, message: str) -> None:
        self.errors.append(message)
        logger.error(message)
    
    def add_checksum(self, table: str, checksum: str) -> None:
        self.checksums[table] = checksum


@dataclass
class DataIntegrityReport:
    """Report on data integrity after migration."""
    source_row_counts: Dict[str, int] = field(default_factory=dict)
    target_row_counts: Dict[str, int] = field(default_factory=dict)
    id_preserved: Dict[str, bool] = field(default_factory=dict)
    timestamp_preserved: Dict[str, bool] = field(default_factory=dict)
    
    def verify(self) -> bool:
        """Verify all integrity checks passed."""
        checks = [
            self._verify_row_counts(),
            self._verify_ids(),
            self._verify_timestamps(),
        ]
        return all(checks)
    
    def _verify_row_counts(self) -> bool:
        """Verify row counts match."""
        for table in self.source_row_counts:
            if self.source_row_counts[table] != self.target_row_counts.get(table, 0):
                logger.error(
                    f"Row count mismatch for {table}: "
                    f"source={self.source_row_counts[table]}, "
                    f"target={self.target_row_counts.get(table, 0)}"
                )
                return False
        return True
    
    def _verify_ids(self) -> bool:
        """Verify IDs preserved."""
        for table, preserved in self.id_preserved.items():
            if not preserved:
                logger.error(f"IDs not preserved for {table}")
                return False
        return True
    
    def _verify_timestamps(self) -> bool:
        """Verify timestamps preserved."""
        for table, preserved in self.timestamp_preserved.items():
            if not preserved:
                logger.error(f"Timestamps not preserved for {table}")
                return False
        return True


def _compute_table_checksum(session: Session, table_name: str) -> str:
    """Compute checksum for a table's data."""
    result = session.execute(text(f"SELECT COUNT(*), GROUP_CONCAT(id) FROM {table_name}"))
    row = result.fetchone()
    if row:
        return hashlib.sha256(f"{row[0]}:{row[1] or ''}".encode()).hexdigest()
    return ""


def _get_row_count(session: Session, table_name: str) -> int:
    """Get row count for a table."""
    result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return result.scalar() or 0


def _check_table_exists(session: Session, table_name: str) -> bool:
    """Check if a table exists."""
    result = session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
    ), {"name": table_name})
    return result.fetchone() is not None


def upgrade(session: Session) -> None:
    """
    Upgrade: Migrate data from legacy backend tables to V2 canonical tables.
    
    This migration:
    1. Checks if backend tables exist
    2. Copies data from backend to V2 tables
    3. Verifies data integrity
    4. Records checksums for rollback verification
    """
    logger.info(f"Running upgrade for migration {MIGRATION_REVISION}")
    
    stats = MigrationStats()
    integrity_report = DataIntegrityReport()
    
    # Check if backend tables exist
    backend_tables_exist = _check_table_exists(session, "chat_sessions")
    
    if not backend_tables_exist:
        logger.info("Legacy backend tables not found, skipping data migration")
        # Still record the migration as completed
        session.execute(text(
            """
            INSERT OR REPLACE INTO migration_history 
            (revision, name, description, applied_at, direction, status)
            VALUES (:revision, :name, :description, :applied_at, :direction, :status)
            """
        ), {
            "revision": MIGRATION_REVISION,
            "name": MIGRATION_NAME,
            "description": MIGRATION_DESCRIPTION,
            "applied_at": "NOW()",
            "direction": "upgrade",
            "status": "completed",
        })
        session.commit()
        return
    
    logger.info("Legacy backend tables found, starting data migration")
    
    # Record source row counts before migration
    source_counts = {
        "chat_sessions": _get_row_count(session, "chat_sessions"),
        "parent_tasks": _get_row_count(session, "parent_tasks"),
        "workflows": _get_row_count(session, "workflows"),
        "workflow_steps": _get_row_count(session, "workflow_steps"),
        "execution_events": _get_row_count(session, "execution_events"),
        "task_artifacts": _get_row_count(session, "task_artifacts"),
    }
    integrity_report.source_row_counts = source_counts
    logger.info(f"Source row counts: {source_counts}")
    
    try:
        # 1. Migrate chat_sessions
        if source_counts["chat_sessions"] > 0:
            logger.info("Migrating chat_sessions...")
            session.execute(text("""
                INSERT OR IGNORE INTO chat_sessions 
                (id, title, status, agent_id, workspace_root, created_at, updated_at, last_event_sequence, metadata_json)
                SELECT 
                    id, title, status, agent_id, workspace_root, 
                    created_at, updated_at, last_event_sequence, metadata_json
                FROM chat_sessions
            """))
            stats.rows_migrated += _get_row_count(session, "chat_sessions")
            stats.tables_migrated += 1
            logger.info("chat_sessions migrated")
        
        # 2. Migrate parent_tasks to v2_tasks
        if source_counts["parent_tasks"] > 0:
            logger.info("Migrating parent_tasks to v2_tasks...")
            session.execute(text("""
                INSERT OR IGNORE INTO v2_tasks 
                (id, prompt, session_id, status, tags_json, created_at)
                SELECT 
                    id, 
                    COALESCE(title, ''),
                    conversation_id,
                    status,
                    json_array(COALESCE(label, '')) as tags_json,
                    created_at
                FROM parent_tasks
            """))
            stats.rows_migrated += _get_row_count(session, "v2_tasks")
            stats.tables_migrated += 1
            logger.info("parent_tasks migrated to v2_tasks")
        
        # 3. Migrate workflows to v2_workflow_runs
        if source_counts["workflows"] > 0:
            logger.info("Migrating workflows to v2_workflow_runs...")
            session.execute(text("""
                INSERT OR IGNORE INTO v2_workflow_runs 
                (run_id, workflow_id, session_id, status, created_at, updated_at)
                SELECT 
                    id, id, session_id, status, created_at, updated_at
                FROM workflows
            """))
            stats.rows_migrated += _get_row_count(session, "v2_workflow_runs")
            stats.tables_migrated += 1
            logger.info("workflows migrated to v2_workflow_runs")
        
        # 4. Migrate workflow_steps to v2_workflow_steps
        if source_counts["workflow_steps"] > 0:
            logger.info("Migrating workflow_steps to v2_workflow_steps...")
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
                    json_object('{}') as result_json,
                    NULL as error
                FROM workflow_steps
            """))
            stats.rows_migrated += _get_row_count(session, "v2_workflow_steps")
            stats.tables_migrated += 1
            logger.info("workflow_steps migrated to v2_workflow_steps")
        
        # 5. Migrate execution_events
        if source_counts["execution_events"] > 0:
            logger.info("Migrating execution_events...")
            # Check if execution_events already exists in V2
            if not _check_table_exists(session, "execution_events"):
                # Table doesn't exist, need to create it first
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS execution_events (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        event_type TEXT NOT NULL,
                        data_json TEXT NOT NULL,
                        event_seq INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                """))
            
            # Migrate data
            session.execute(text("""
                INSERT OR IGNORE INTO execution_events 
                (id, session_id, event_type, data_json, event_seq, created_at)
                SELECT 
                    id, session_id, event_type, data_json, event_seq, created_at
                FROM execution_events
            """))
            stats.rows_migrated += _get_row_count(session, "execution_events")
            stats.tables_migrated += 1
            logger.info("execution_events migrated")
        
        # 6. Migrate task_artifacts to v2_artifacts
        if source_counts["task_artifacts"] > 0:
            logger.info("Migrating task_artifacts to v2_artifacts...")
            session.execute(text("""
                INSERT OR IGNORE INTO v2_artifacts 
                (id, artifact_type, uri, metadata_json, checksum, created_at)
                SELECT 
                    id, 
                    artifact_type,
                    path_or_uri,
                    metadata_json,
                    checksum,
                    created_at
                FROM task_artifacts
            """))
            stats.rows_migrated += _get_row_count(session, "v2_artifacts")
            stats.tables_migrated += 1
            logger.info("task_artifacts migrated to v2_artifacts")
        
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
        
        # Verify data integrity
        if integrity_report.verify():
            logger.info("Data integrity verification PASSED")
        else:
            logger.error("Data integrity verification FAILED")
            stats.add_error("Data integrity verification failed")
        
        # Record checksums
        for table in ["chat_sessions", "v2_tasks", "v2_workflow_runs", 
                      "v2_workflow_steps", "execution_events", "v2_artifacts"]:
            checksum = _compute_table_checksum(session, table)
            stats.add_checksum(table, checksum)
        
        # Record migration in history
        session.execute(text(
            """
            INSERT OR REPLACE INTO migration_history 
            (revision, name, description, applied_at, direction, checksum, status)
            VALUES (:revision, :name, :description, :applied_at, :direction, :checksum, :status)
            """
        ), {
            "revision": MIGRATION_REVISION,
            "name": MIGRATION_NAME,
            "description": MIGRATION_DESCRIPTION,
            "applied_at": "NOW()",
            "direction": "upgrade",
            "checksum": json.dumps(stats.checksums),
            "status": "completed" if not stats.errors else "failed",
        })
        
        session.commit()
        logger.info(
            f"Migration {MIGRATION_REVISION} upgrade completed. "
            f"Migrated {stats.rows_migrated} rows across {stats.tables_migrated} tables"
        )
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        session.rollback()
        
        # Record failed migration
        session.execute(text(
            """
            INSERT OR REPLACE INTO migration_history 
            (revision, name, description, applied_at, direction, status)
            VALUES (:revision, :name, :description, :applied_at, :direction, :status)
            """
        ), {
            "revision": MIGRATION_REVISION,
            "name": MIGRATION_NAME,
            "description": MIGRATION_DESCRIPTION,
            "applied_at": "NOW()",
            "direction": "upgrade",
            "status": "failed",
        })
        session.commit()
        raise


def downgrade(session: Session) -> None:
    """
    Downgrade: Remove data migrated in upgrade.
    
    This is a NO-OP for safety reasons. To properly rollback:
    1. Restore from backup
    2. Run migration_001 downgrade
    
    We do NOT automatically delete data to prevent accidental data loss.
    """
    logger.info(f"Running downgrade for migration {MIGRATION_REVISION}")
    
    # Mark migration as downgraded but don't delete data
    session.execute(text(
        """
        UPDATE migration_history 
        SET direction = :direction, status = :status
        WHERE revision = :revision
        """
    ), {
        "revision": MIGRATION_REVISION,
        "direction": "downgrade",
        "status": "rolled_back",
    })
    
    session.commit()
    logger.info(
        f"Migration {MIGRATION_REVISION} downgrade completed. "
        f"Data NOT deleted - restore from backup to rollback completely"
    )
