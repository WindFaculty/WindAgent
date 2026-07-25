"""
Backup Manager for WindAgent Storage Layer.
Creates and manages database backups before migrations.
"""

from __future__ import annotations
import gzip
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

logger = logging.getLogger("windagent.storage.migrations.backup")


@dataclass
class BackupInfo:
    """Information about a backup."""
    backup_id: str
    database_path: str
    backup_path: str
    created_at: datetime
    size_bytes: int
    schema_checksum: str
    row_counts: Dict[str, int] = field(default_factory=dict)
    is_compressed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "database_path": self.database_path,
            "backup_path": self.backup_path,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "schema_checksum": self.schema_checksum,
            "row_counts": self.row_counts,
            "is_compressed": self.is_compressed,
        }


class BackupManager:
    """
    Manages database backups for migration safety.
    
    Features:
    - Create backups before migrations
    - Restore from backups
    - List available backups
    - Clean up old backups
    - Compressed backups
    - Row count verification
    """
    
    BACKUP_DIR_NAME = "db_backups"
    DEFAULT_RETENTION_DAYS = 30
    
    def __init__(self, backup_root: Optional[Path] = None):
        self._backup_root = backup_root or Path.cwd() / self.BACKUP_DIR_NAME
        self._backup_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup root: {self._backup_root}")
    
    def _get_backup_dir(self, backup_id: str) -> Path:
        """Get directory for a specific backup."""
        return self._backup_root / backup_id
    
    def create_backup(
        self,
        engine: Engine,
        backup_id: Optional[str] = None,
        compress: bool = True,
        include_row_counts: bool = True,
    ) -> BackupInfo:
        """
        Create a backup of the database.
        
        Args:
            engine: SQLAlchemy engine
            backup_id: Optional backup ID (defaults to timestamp)
            compress: Whether to compress the backup
            include_row_counts: Whether to include row counts in backup info
            
        Returns:
            BackupInfo with backup details
        """
        backup_id = backup_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._get_backup_dir(backup_id)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Get database path
        database_path = self._get_database_path(engine)
        
        # Copy database file
        backup_path = backup_dir / "database.sqlite3"
        shutil.copy2(database_path, backup_path)
        
        # Compress if requested
        if compress:
            compressed_path = backup_path.with_suffix(".sqlite3.gz")
            with open(backup_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.write(f_in.read())
            backup_path.unlink()
            backup_path = compressed_path
        
        # Get file size
        size_bytes = backup_path.stat().st_size
        
        # Compute schema checksum
        schema_checksum = self._compute_schema_checksum(engine)
        
        # Get row counts if requested
        row_counts: Dict[str, int] = {}
        if include_row_counts:
            row_counts = self._get_row_counts(engine)
        
        # Create backup info
        backup_info = BackupInfo(
            backup_id=backup_id,
            database_path=str(database_path),
            backup_path=str(backup_path),
            created_at=datetime.now(),
            size_bytes=size_bytes,
            schema_checksum=schema_checksum,
            row_counts=row_counts,
            is_compressed=compress,
        )
        
        # Save backup metadata
        metadata_path = backup_dir / "backup_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(backup_info.to_dict(), f, indent=2)
        
        logger.info(f"Created backup {backup_id} ({size_bytes} bytes)")
        return backup_info
    
    def restore_backup(
        self,
        backup_id: str,
        engine: Engine,
        verify_row_counts: bool = True,
    ) -> bool:
        """
        Restore database from a backup.
        
        Args:
            backup_id: Backup ID to restore
            engine: SQLAlchemy engine
            verify_row_counts: Whether to verify row counts after restore
            
        Returns:
            True if restore successful
        """
        backup_dir = self._get_backup_dir(backup_id)
        metadata_path = backup_dir / "backup_metadata.json"
        
        if not metadata_path.exists():
            logger.error(f"Backup {backup_id} not found")
            return False
        
        # Load backup metadata
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        # Find backup file
        backup_path = Path(metadata["backup_path"])
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        # Get target database path
        database_path = self._get_database_path(engine)
        
        # Close all connections to the database
        engine.dispose()
        
        # Restore from backup
        if metadata.get("is_compressed", False):
            # Decompress
            with gzip.open(backup_path, "rb") as f_in:
                with open(database_path, "wb") as f_out:
                    f_out.write(f_in.read())
        else:
            # Copy directly
            shutil.copy2(backup_path, database_path)
        
        # Verify row counts if requested
        if verify_row_counts:
            original_counts = metadata.get("row_counts", {})
            current_counts = self._get_row_counts(engine)
            
            for table, count in original_counts.items():
                if current_counts.get(table) != count:
                    logger.warning(
                        f"Row count mismatch for {table}: "
                        f"expected {count}, got {current_counts.get(table)}"
                    )
        
        logger.info(f"Restored backup {backup_id}")
        return True
    
    def list_backups(self) -> List[BackupInfo]:
        """List all available backups."""
        backups = []
        
        for backup_dir in self._backup_root.iterdir():
            if not backup_dir.is_dir():
                continue
            
            metadata_path = backup_dir / "backup_metadata.json"
            if not metadata_path.exists():
                continue
            
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                
                backup = BackupInfo(
                    backup_id=metadata["backup_id"],
                    database_path=metadata["database_path"],
                    backup_path=metadata["backup_path"],
                    created_at=datetime.fromisoformat(metadata["created_at"]),
                    size_bytes=metadata["size_bytes"],
                    schema_checksum=metadata["schema_checksum"],
                    row_counts=metadata.get("row_counts", {}),
                    is_compressed=metadata.get("is_compressed", False),
                )
                backups.append(backup)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load backup metadata: {e}")
        
        # Sort by created_at descending
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups
    
    def cleanup_old_backups(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        """
        Clean up backups older than retention period.
        
        Args:
            retention_days: Number of days to retain backups
            
        Returns:
            Number of backups deleted
        """
        cutoff = datetime.now().replace(
            day=datetime.now().day - retention_days,
            hour=0, minute=0, second=0, microsecond=0
        )
        
        deleted_count = 0
        for backup in self.list_backups():
            if backup.created_at < cutoff:
                backup_dir = self._get_backup_dir(backup.backup_id)
                shutil.rmtree(backup_dir, ignore_errors=True)
                deleted_count += 1
                logger.info(f"Deleted old backup {backup.backup_id}")
        
        return deleted_count
    
    def get_latest_backup(self) -> Optional[BackupInfo]:
        """Get the most recent backup."""
        backups = self.list_backups()
        return backups[0] if backups else None
    
    def _get_database_path(self, engine: Engine) -> Path:
        """Get the database file path from engine."""
        # For SQLite
        if hasattr(engine, "url") and str(engine.url).startswith("sqlite"):
            db_path = str(engine.url).replace("sqlite:///", "")
            return Path(db_path)
        else:
            raise ValueError("Unsupported database type for backup")
    
    def _compute_schema_checksum(self, engine: Engine) -> str:
        """Compute schema checksum for the database."""
        from windagent_storage.migrations.schema_checksum import SchemaChecksum
        return SchemaChecksum.compute_checksum_from_engine(engine)
    
    def _get_row_counts(self, engine: Engine) -> Dict[str, int]:
        """Get row counts for all tables."""
        row_counts = {}
        
        with engine.connect() as conn:
            # Get all tables
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ))
            
            for row in result:
                table_name = row[0]
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_counts[table_name] = count_result.scalar()
        
        return row_counts
