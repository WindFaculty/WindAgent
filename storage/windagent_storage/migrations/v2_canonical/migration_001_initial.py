"""
Migration 001: Initial V2 Canonical Schema
Creates the initial V2 canonical tables and migration history tracking.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from windagent_storage.orm.models import (
    BaseORM,
    SessionORM,
    TaskORM,
    WorkflowRunORM,
    WorkflowStepORM,
    ExecutionEventORM,
    OutboxRecordORM,
    ArtifactRefORM,
    ProviderConfigORM,
)

logger = logging.getLogger("windagent.storage.migrations.001")

MIGRATION_REVISION = "001_initial"
MIGRATION_NAME = "Initial V2 Canonical Schema"
MIGRATION_DESCRIPTION = """
Creates the initial V2 canonical tables:
- chat_sessions (SessionORM)
- v2_tasks (TaskORM)
- v2_workflow_runs (WorkflowRunORM)
- v2_workflow_steps (WorkflowStepORM)
- execution_events (ExecutionEventORM)
- v2_outbox_records (OutboxRecordORM)
- v2_artifacts (ArtifactRefORM)
- v2_provider_configs (ProviderConfigORM)

Also creates migration history table for tracking.
"""


# Migration history table DDL
MIGRATION_HISTORY_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS migration_history (
    revision TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    applied_at TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'upgrade' or 'downgrade'
    checksum TEXT,
    status TEXT NOT NULL DEFAULT 'completed'
)
"""


def upgrade(session: Session) -> None:
    """
    Upgrade: Create V2 canonical tables and migration history table.
    
    This is a safe operation - it only creates tables that don't exist.
    No data is modified or deleted.
    """
    logger.info(f"Running upgrade for migration {MIGRATION_REVISION}")
    
    # Create migration history table first
    session.execute(text(MIGRATION_HISTORY_TABLE_DDL))
    
    # Create all V2 canonical tables using SQLAlchemy metadata
    metadata = BaseORM.metadata
    
    # Create tables that don't exist
    created_tables: List[str] = []
    
    # Check and create each table
    tables_to_create = [
        SessionORM.__table__,
        TaskORM.__table__,
        WorkflowRunORM.__table__,
        WorkflowStepORM.__table__,
        ExecutionEventORM.__table__,
        OutboxRecordORM.__table__,
        ArtifactRefORM.__table__,
        ProviderConfigORM.__table__,
    ]
    
    for table in tables_to_create:
        table_name = table.name
        
        # Check if table exists
        result = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
        ), {"name": table_name})
        
        if result.fetchone() is None:
            # Table doesn't exist, create it
            table.create(session.get_bind())
            created_tables.append(table_name)
            logger.info(f"Created table: {table_name}")
        else:
            logger.debug(f"Table already exists: {table_name}, skipping")
    
    # Record this migration in history
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
    logger.info(f"Migration {MIGRATION_REVISION} upgrade completed. Created tables: {created_tables}")


def downgrade(session: Session) -> None:
    """
    Downgrade: Drop V2 canonical tables.
    
    WARNING: This will DELETE all data in V2 tables!
    Only use for rollback testing.
    """
    logger.info(f"Running downgrade for migration {MIGRATION_REVISION}")
    
    # Drop tables in reverse order to handle foreign keys
    tables_to_drop = [
        "v2_artifacts",
        "v2_workflow_steps",
        "v2_workflow_runs",
        "v2_tasks",
        "v2_outbox_records",
        "v2_provider_configs",
        "execution_events",
        "chat_sessions",
    ]
    
    dropped_tables: List[str] = []
    
    for table_name in tables_to_drop:
        try:
            session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            dropped_tables.append(table_name)
            logger.info(f"Dropped table: {table_name}")
        except Exception as e:
            logger.warning(f"Failed to drop table {table_name}: {e}")
    
    # Remove migration history record
    session.execute(text(
        "DELETE FROM migration_history WHERE revision = :revision"
    ), {"revision": MIGRATION_REVISION})
    
    session.commit()
    logger.info(f"Migration {MIGRATION_REVISION} downgrade completed. Dropped tables: {dropped_tables}")
