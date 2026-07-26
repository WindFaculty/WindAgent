"""Backup Manager for WindAgent Storage Layer (Phase 9).
Creates and manages database backups with file checksum, schema checksum, and row count verification.
"""

from __future__ import annotations
import gzip
import hashlib
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import Engine, text

logger = logging.getLogger("windagent.storage.migrations.backup")


def _compute_file_checksum(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class BackupInfo:
    """Information about a backup."""
    backup_id: str
    database_path: str
    backup_path: str
    created_at: datetime
    size_bytes: int
    schema_checksum: str
    file_checksum: str = ""
    migration_revision: str = "002_legacy_data"
    app_version: str = "0.3.0"
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
            "file_checksum": self.file_checksum,
            "migration_revision": self.migration_revision,
            "app_version": self.app_version,
            "row_counts": self.row_counts,
            "is_compressed": self.is_compressed,
        }


class BackupManager:
    """Manages database backups for migration safety and rollback rehearsals."""

    BACKUP_DIR_NAME = "db_backups"
    DEFAULT_RETENTION_DAYS = 30

    def __init__(self, backup_root: Optional[Path] = None):
        self._backup_root = backup_root or Path.cwd() / self.BACKUP_DIR_NAME
        self._backup_root.mkdir(parents=True, exist_ok=True)

    def _get_backup_dir(self, backup_id: str) -> Path:
        return self._backup_root / backup_id

    def create_backup(
        self,
        engine: Engine,
        backup_id: Optional[str] = None,
        compress: bool = True,
        include_row_counts: bool = True,
        migration_revision: str = "002_legacy_data",
        app_version: str = "0.3.0",
    ) -> BackupInfo:
        """Create a backup of the database with file and schema checksums."""
        backup_id = backup_id or (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:8]}"
        )
        backup_dir = self._get_backup_dir(backup_id)
        backup_dir.mkdir(parents=True, exist_ok=True)

        database_path = self._get_database_path(engine)
        backup_path = backup_dir / "database.sqlite3"
        shutil.copy2(database_path, backup_path)

        if compress:
            compressed_path = backup_path.with_suffix(".sqlite3.gz")
            with open(backup_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.write(f_in.read())
            backup_path.unlink()
            backup_path = compressed_path

        size_bytes = backup_path.stat().st_size
        file_checksum = _compute_file_checksum(backup_path)
        schema_checksum = self._compute_schema_checksum(engine)

        row_counts: Dict[str, int] = {}
        if include_row_counts:
            row_counts = self._get_row_counts(engine)

        backup_info = BackupInfo(
            backup_id=backup_id,
            database_path=str(database_path),
            backup_path=str(backup_path),
            created_at=datetime.now(),
            size_bytes=size_bytes,
            schema_checksum=schema_checksum,
            file_checksum=file_checksum,
            migration_revision=migration_revision,
            app_version=app_version,
            row_counts=row_counts,
            is_compressed=compress,
        )

        metadata_path = backup_dir / "backup_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(backup_info.to_dict(), f, indent=2)

        logger.info(f"Created backup {backup_id} ({size_bytes} bytes, file_checksum={file_checksum[:8]})")
        return backup_info

    def restore_backup(
        self,
        backup_id: str,
        engine: Engine,
        verify_file_checksum: bool = True,
        verify_row_counts: bool = True,
        verify_schema_checksum: bool = True,
    ) -> bool:
        """Restore database from a backup with strict integrity checks."""
        backup_dir = self._get_backup_dir(backup_id)
        metadata_path = backup_dir / "backup_metadata.json"

        if not metadata_path.exists():
            logger.error(f"Backup metadata not found for backup_id={backup_id}")
            return False

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        backup_path = Path(metadata["backup_path"])
        if not backup_path.exists():
            logger.error(f"Backup file not found at path: {backup_path}")
            return False

        # 1. Verify backup file checksum before restore
        if verify_file_checksum and metadata.get("file_checksum"):
            actual_checksum = _compute_file_checksum(backup_path)
            if actual_checksum != metadata["file_checksum"]:
                logger.error(
                    f"Backup file checksum verification failed for {backup_id}: "
                    f"expected {metadata['file_checksum']}, got {actual_checksum}"
                )
                return False

        database_path = self._get_database_path(engine)
        engine.dispose()

        # 2. Restore file
        if metadata.get("is_compressed", False):
            with gzip.open(backup_path, "rb") as f_in:
                with open(database_path, "wb") as f_out:
                    f_out.write(f_in.read())
        else:
            shutil.copy2(backup_path, database_path)

        # 3. Verify schema checksum after restore
        if verify_schema_checksum and metadata.get("schema_checksum"):
            restored_schema_checksum = self._compute_schema_checksum(engine)
            if restored_schema_checksum != metadata["schema_checksum"]:
                logger.error(
                    f"Restored schema checksum mismatch for {backup_id}: "
                    f"expected {metadata['schema_checksum']}, got {restored_schema_checksum}"
                )
                return False

        # 4. Verify row counts after restore
        if verify_row_counts and metadata.get("row_counts"):
            original_counts = metadata["row_counts"]
            current_counts = self._get_row_counts(engine)
            for table, expected_count in original_counts.items():
                actual_count = current_counts.get(table, 0)
                if actual_count != expected_count:
                    logger.error(
                        f"Restored row count mismatch for {table}: "
                        f"expected {expected_count}, got {actual_count}"
                    )
                    return False

        logger.info(f"Restored backup {backup_id} successfully.")
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
                    schema_checksum=metadata.get("schema_checksum", ""),
                    file_checksum=metadata.get("file_checksum", ""),
                    migration_revision=metadata.get("migration_revision", "002_legacy_data"),
                    app_version=metadata.get("app_version", "0.3.0"),
                    row_counts=metadata.get("row_counts", {}),
                    is_compressed=metadata.get("is_compressed", False),
                )
                backups.append(backup)
            except Exception as e:
                logger.warning(f"Failed to load backup metadata for {backup_dir}: {e}")
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    def cleanup_old_backups(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        cutoff = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        for backup in self.list_backups():
            if backup.created_at < cutoff:
                backup_dir = self._get_backup_dir(backup.backup_id)
                shutil.rmtree(backup_dir, ignore_errors=True)
                deleted_count += 1
        return deleted_count

    def get_latest_backup(self) -> Optional[BackupInfo]:
        backups = self.list_backups()
        return backups[0] if backups else None

    def _get_database_path(self, engine: Engine) -> Path:
        if hasattr(engine, "url") and str(engine.url).startswith("sqlite"):
            db_path = str(engine.url).replace("sqlite:///", "")
            return Path(db_path)
        else:
            raise ValueError("Unsupported database type for backup")

    def _compute_schema_checksum(self, engine: Engine) -> str:
        from windagent_storage.migrations.schema_checksum import SchemaChecksum
        return SchemaChecksum.compute_checksum_from_engine(engine)

    def _get_row_counts(self, engine: Engine) -> Dict[str, int]:
        row_counts = {}
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            )
            for row in result:
                table_name = row[0]
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_counts[table_name] = count_result.scalar() or 0
        return row_counts
