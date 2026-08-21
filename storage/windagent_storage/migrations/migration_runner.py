"""
Migration Runner for WindAgent Storage Layer.
Orchestrates migration execution with locking, backup, and verification.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from windagent_storage.migrations.migration_registry import (
    migration_registry,
)
from windagent_storage.migrations.migration_lock import MigrationLock, LockType
from windagent_storage.factory import create_backup_manager
from windagent_storage.migrations.schema_checksum import SchemaChecksum

# Import migrations
from windagent_storage.migrations.v2_canonical.migration_001_initial import (
    upgrade as upgrade_001,
    downgrade as downgrade_001,
    MIGRATION_REVISION as REVISION_001,
    MIGRATION_NAME as NAME_001,
    MIGRATION_DESCRIPTION as DESC_001,
)
from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import (
    upgrade as upgrade_002,
    downgrade as downgrade_002,
    MIGRATION_REVISION as REVISION_002,
    MIGRATION_NAME as NAME_002,
    MIGRATION_DESCRIPTION as DESC_002,
)

logger = logging.getLogger("windagent.storage.migrations.runner")


class MigrationRunner:
    """
    Runs database migrations with safety features.
    
    Features:
    - Automatic locking to prevent concurrent migrations
    - Automatic backup before migration
    - Schema checksum verification
    - Rollback support
    - Migration history tracking
    """
    
    def __init__(
        self,
        database_url: str,
        backup_root: Optional[str] = None,
        lock_timeout: int = 300,
    ):
        """
        Initialize migration runner.
        
        Args:
            database_url: SQLAlchemy database URL
            backup_root: Optional backup directory path
            lock_timeout: Lock timeout in seconds
        """
        self._database_url = database_url
        self._engine: Optional[Engine] = None
        self._backup_manager = create_backup_manager(backup_root)
        self._lock: Optional[MigrationLock] = None
        self._lock_timeout = lock_timeout
        
        # Register migrations
        self._register_migrations()
    
    def _register_migrations(self) -> None:
        """Register all migrations with the registry."""
        # Migration 001: Initial V2 Canonical Schema
        migration_registry.register(
            revision=REVISION_001,
            name=NAME_001,
            description=DESC_001,
            upgrade=upgrade_001,
            downgrade=downgrade_001,
            dependencies=[],
        )
        
        # Migration 002: Legacy Data Migration
        migration_registry.register(
            revision=REVISION_002,
            name=NAME_002,
            description=DESC_002,
            upgrade=upgrade_002,
            downgrade=downgrade_002,
            dependencies=[REVISION_001],
        )
        
        logger.info(f"Registered {len(migration_registry.get_all_revisions())} migrations")
    
    @property
    def engine(self) -> Engine:
        """Get or create database engine."""
        if self._engine is None:
            self._engine = create_engine(self._database_url)
        return self._engine
    
    @property
    def lock(self) -> MigrationLock:
        """Get or create migration lock."""
        if self._lock is None:
            self._lock = MigrationLock(self.engine, self._lock_timeout)
        return self._lock
    
    def get_pending_migrations(self) -> List[str]:
        """Get list of pending migrations."""
        return migration_registry.get_pending_migrations(self.engine)
    
    def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """Get list of applied migrations."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT revision, name, direction, status, applied_at, checksum
                FROM migration_history
                ORDER BY applied_at
            """))
            
            migrations = []
            for row in result:
                migrations.append({
                    "revision": row[0],
                    "name": row[1],
                    "direction": row[2],
                    "status": row[3],
                    "applied_at": row[4],
                    "checksum": row[5],
                })
            return migrations
    
    def run_all_migrations(self, backup: bool = True) -> Dict[str, Any]:
        """
        Run all pending migrations.
        
        Args:
            backup: Whether to create backup before migrations
            
        Returns:
            Result dictionary with migration results
        """
        result: Dict[str, Any] = {
            "migrations_run": [],
            "errors": [],
            "backup_info": None,
        }
        
        try:
            # Acquire lock
            with self.lock.acquire_context(LockType.MIGRATION):
                # Create backup before migrations
                if backup:
                    backup_info = self._backup_manager.create_backup(self.engine)
                    result["backup_info"] = backup_info.to_dict()
                    logger.info(f"Created backup: {backup_info.backup_id}")
                
                # Get pending migrations
                pending = migration_registry.get_pending_migrations(self.engine)
                
                if not pending:
                    logger.info("No pending migrations")
                    result["status"] = "no_migrations"
                    return result
                
                logger.info(f"Running {len(pending)} pending migrations: {pending}")
                
                # Run each migration in order
                for revision in pending:
                    migration_result = self.run_migration(revision)
                    result["migrations_run"].append(migration_result)
                    
                    if migration_result["status"] == "failed":
                        result["errors"].append(migration_result)
                        logger.error(f"Migration {revision} failed")
                        break
                
                result["status"] = "completed" if not result["errors"] else "failed"
                return result
        
        except Exception as e:
            logger.error(f"Migration run failed: {e}")
            result["status"] = "failed"
            result["errors"].append({"error": str(e)})
            raise
    
    def run_migration(self, revision: str) -> Dict[str, Any]:
        """
        Run a single migration.
        
        Args:
            revision: Migration revision to run
            
        Returns:
            Result dictionary
        """
        result: Dict[str, Any] = {
            "revision": revision,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
        
        try:
            import time
            start_time = time.time()
            result["started_at"] = start_time
            
            # Get migration spec
            spec = migration_registry.get_migration(revision)
            upgrade_fn = migration_registry.get_upgrade_function(revision)
            
            logger.info(f"Running migration {revision}: {spec.name}")
            
            # Compute pre-migration checksum
            pre_checksum = SchemaChecksum.compute_checksum_from_engine(self.engine)
            
            # Execute migration
            with Session(self.engine) as session:
                upgrade_fn(session)
            
            # Compute post-migration checksum
            post_checksum = SchemaChecksum.compute_checksum_from_engine(self.engine)
            
            end_time = time.time()
            result["completed_at"] = end_time
            result["duration"] = end_time - start_time
            result["pre_checksum"] = pre_checksum
            result["post_checksum"] = post_checksum
            result["status"] = "completed"
            
            logger.info(f"Migration {revision} completed in {result['duration']:.2f}s")
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Migration {revision} failed: {e}")
            raise
    
    def rollback_migration(self, revision: str) -> Dict[str, Any]:
        """
        Rollback a single migration.
        
        Args:
            revision: Migration revision to rollback
            
        Returns:
            Result dictionary
        """
        result: Dict[str, Any] = {
            "revision": revision,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
        
        try:
            import time
            start_time = time.time()
            result["started_at"] = start_time
            
            # Get migration spec
            spec = migration_registry.get_migration(revision)
            downgrade_fn = migration_registry.get_downgrade_function(revision)
            
            logger.info(f"Rolling back migration {revision}: {spec.name}")
            
            # Compute pre-rollback checksum
            pre_checksum = SchemaChecksum.compute_checksum_from_engine(self.engine)
            
            # Execute downgrade
            with Session(self.engine) as session:
                downgrade_fn(session)
            
            # Compute post-rollback checksum
            post_checksum = SchemaChecksum.compute_checksum_from_engine(self.engine)
            
            end_time = time.time()
            result["completed_at"] = end_time
            result["duration"] = end_time - start_time
            result["pre_checksum"] = pre_checksum
            result["post_checksum"] = post_checksum
            result["status"] = "completed"
            
            logger.info(f"Migration {revision} rolled back in {result['duration']:.2f}s")
            return result
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Migration {revision} rollback failed: {e}")
            raise
    
    def verify_migrations(self) -> Dict[str, Any]:
        """
        Verify all migrations are applied correctly.
        
        Returns:
            Verification result
        """
        result: Dict[str, Any] = {
            "status": "ok",
            "applied": [],
            "pending": [],
            "errors": [],
        }
        
        try:
            pending = migration_registry.get_pending_migrations(self.engine)
            applied = self.get_applied_migrations()
            
            result["applied"] = [m["revision"] for m in applied]
            result["pending"] = pending
            
            # Check for failed migrations
            failed = [m for m in applied if m["status"] == "failed"]
            if failed:
                result["status"] = "failed"
                result["errors"].extend(failed)
            
            # Check if all migrations are applied
            if len(pending) > 0:
                result["status"] = "pending"
            
            return result
        
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            raise
    
    def get_schema_checksum(self) -> str:
        """Get current schema checksum."""
        return SchemaChecksum.compute_checksum_from_engine(self.engine)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self._engine:
            self._engine.dispose()
            self._engine = None


# Convenience function
migration_runner: Optional[MigrationRunner] = None


def get_migration_runner(database_url: str) -> MigrationRunner:
    """Get or create global migration runner."""
    global migration_runner
    if migration_runner is None:
        migration_runner = MigrationRunner(database_url)
    return migration_runner
