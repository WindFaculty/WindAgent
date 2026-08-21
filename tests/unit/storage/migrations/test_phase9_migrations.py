"""
Test suite for PHASE 9 — Migration du lieu va schema rollback (Data Migration and Schema Rollback)

This test suite verifies that:
1. Schema checksums are computed correctly
2. Migration locks work correctly
3. Backup manager works correctly
4. Migrations can be applied and rolled back
5. Data integrity is preserved during migration
"""

import json
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from windagent_storage.migrations.schema_checksum import SchemaChecksum
from windagent_storage.migrations.migration_lock import MigrationLock, LockType, LockStatus
from windagent_storage.migrations.backup_manager import BackupManager
from windagent_storage.migrations.migration_registry import (
    migration_registry,
)
from windagent_storage.orm.models import BaseORM


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create all tables
    BaseORM.metadata.create_all(engine)
    
    yield engine, db_path
    
    # Cleanup
    engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_db_with_backend_tables():
    """Create a temporary SQLite database with legacy backend tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create legacy backend tables
    with engine.connect() as conn:
        # chat_sessions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT DEFAULT 'idle',
                agent_id TEXT,
                workspace_root TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_event_sequence INTEGER DEFAULT 0,
                metadata_json TEXT
            )
        """))
        
        # parent_tasks
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS parent_tasks (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                title TEXT,
                status TEXT DEFAULT 'draft',
                label TEXT,
                progress REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # workflows
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # workflow_steps
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                step_type TEXT,
                name TEXT,
                tool_name TEXT,
                params_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                order_index INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # execution_events
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS execution_events (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                event_type TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                event_seq INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # task_artifacts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                agent_instance_id TEXT,
                artifact_type TEXT,
                path_or_uri TEXT,
                metadata_json TEXT DEFAULT '{}',
                checksum TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.commit()
    
    yield engine, db_path
    
    # Cleanup
    engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def backup_manager(tmp_path):
    """Keep backup artifacts isolated from the repository worktree."""
    return BackupManager(backup_root=tmp_path / "db_backups")


class TestSchemaChecksum:
    """Test schema checksum computation."""
    
    def test_compute_schema_checksum(self, temp_db):
        """Test that schema checksum is computed correctly."""
        engine, _ = temp_db
        
        checksum1 = SchemaChecksum.compute_checksum_from_orm_base(BaseORM)
        checksum2 = SchemaChecksum.compute_checksum_from_engine(engine)
        
        # Both methods should produce the same checksum
        assert checksum1 == checksum2
        
        # Checksum should be a valid SHA256 hex string
        assert len(checksum1) == 64
        assert all(c in "0123456789abcdef" for c in checksum1)
    
    def test_checksum_detects_schema_change(self, temp_db):
        """Test that checksum changes when schema changes."""
        engine, _ = temp_db
        
        checksum1 = SchemaChecksum.compute_checksum_from_engine(engine)
        
        # Add a new table
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE test_table (
                    id TEXT PRIMARY KEY,
                    name TEXT
                )
            """))
            conn.commit()
        
        checksum2 = SchemaChecksum.compute_checksum_from_engine(engine)
        
        # Checksum should be different
        assert checksum1 != checksum2
    
    def test_get_schema_snapshot(self, temp_db):
        """Test getting complete schema snapshot."""
        engine, _ = temp_db
        metadata = BaseORM.metadata
        
        snapshot = SchemaChecksum.get_schema_snapshot(metadata)
        
        assert "tables" in snapshot
        assert "checksum" in snapshot
        assert len(snapshot["tables"]) > 0
        
        # Check that each table has expected fields
        for table_name, table_info in snapshot["tables"].items():
            assert "columns" in table_info
            assert "primary_key" in table_info
            assert "foreign_keys" in table_info
            assert "indexes" in table_info


class TestMigrationLock:
    """Test migration locking."""
    
    def test_acquire_and_release_lock(self, temp_db):
        """Test acquiring and releasing a lock."""
        engine, _ = temp_db
        lock = MigrationLock(engine)
        
        # Acquire lock
        assert lock.acquire(LockType.MIGRATION)
        assert lock.is_locked(LockType.MIGRATION)
        
        # Release lock
        assert lock.release()
        assert not lock.is_locked(LockType.MIGRATION)
    
    def test_lock_context_manager(self, temp_db):
        """Test lock as context manager."""
        engine, _ = temp_db
        lock = MigrationLock(engine)
        
        with lock.acquire_context(LockType.MIGRATION):
            assert lock.is_locked(LockType.MIGRATION)
        
        assert not lock.is_locked(LockType.MIGRATION)
    
    def test_multiple_locks(self, temp_db):
        """Test multiple lock types."""
        engine, _ = temp_db
        lock = MigrationLock(engine)
        
        # Acquire different lock types
        assert lock.acquire(LockType.MIGRATION)
        assert lock.acquire(LockType.SCHEMA_CHECK)
        
        # Both should be locked
        assert lock.is_locked(LockType.MIGRATION)
        assert lock.is_locked(LockType.SCHEMA_CHECK)
        
        # Release all
        assert lock.release()  # Releases MIGRATION
        assert lock.release()  # Releases SCHEMA_CHECK
    
    def test_lock_cleanup(self, temp_db):
        """Test lock cleanup."""
        engine, _ = temp_db
        lock = MigrationLock(engine)
        
        # Manually insert an expired lock
        with engine.connect() as conn:
            expired_time = (datetime.now() - timedelta(seconds=3600)).isoformat()
            conn.execute(text("""
                INSERT INTO migration_locks 
                (lock_id, lock_type, acquired_by, acquired_at, expires_at, status)
                VALUES (:lock_id, :lock_type, :acquired_by, :acquired_at, :expires_at, :status)
            """), {
                "lock_id": "test-expired-lock",
                "lock_type": LockType.MIGRATION.value,
                "acquired_by": "test",
                "acquired_at": expired_time,
                "expires_at": expired_time,
                "status": LockStatus.ACQUIRED.value,
            })
            conn.commit()
        
        # Cleanup expired locks
        cleaned = lock.cleanup_expired()
        assert cleaned >= 1
        
        # Verify lock is marked as expired
        locks = lock.get_active_locks()
        expired_locks = [lock_item for lock_item in locks if lock_item.lock_id == "test-expired-lock"]
        assert len(expired_locks) == 0


class TestBackupManager:
    """Test backup manager."""
    
    def test_create_backup(self, temp_db, backup_manager):
        """Test creating a backup."""
        engine, db_path = temp_db
        
        # Insert some test data
        with Session(engine) as session:
            session.execute(text("""
                INSERT INTO chat_sessions
                (id, title, status, created_at, updated_at, last_event_sequence)
                VALUES
                ('test-id', 'Test Session', 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
            """))
            session.commit()
        
        # Create backup
        backup_info = backup_manager.create_backup(engine)
        
        assert backup_info is not None
        assert backup_info.backup_id is not None
        assert backup_info.size_bytes > 0
        assert backup_info.schema_checksum is not None
        assert len(backup_info.row_counts) > 0
    
    def test_list_backups(self, temp_db, backup_manager):
        """Test listing backups."""
        engine, db_path = temp_db
        # Create a backup
        backup_info = backup_manager.create_backup(engine)
        
        # List backups
        backups = backup_manager.list_backups()
        
        assert len(backups) >= 1
        assert any(b.backup_id == backup_info.backup_id for b in backups)
    
    def test_get_latest_backup(self, temp_db, backup_manager):
        """Test getting latest backup."""
        engine, db_path = temp_db
        # Create a backup
        backup_info = backup_manager.create_backup(engine)
        
        # Get latest
        latest = backup_manager.get_latest_backup()
        
        assert latest is not None
        assert latest.backup_id == backup_info.backup_id
    
    def test_backup_metadata(self, temp_db, backup_manager):
        """Test backup metadata is saved correctly."""
        engine, db_path = temp_db
        # Create a backup
        backup_info = backup_manager.create_backup(engine)
        
        # Verify metadata file exists
        backup_dir = Path(backup_manager._backup_root) / backup_info.backup_id
        metadata_path = backup_dir / "backup_metadata.json"
        
        assert metadata_path.exists()
        
        # Verify metadata content
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        assert metadata["backup_id"] == backup_info.backup_id
        assert metadata["size_bytes"] == backup_info.size_bytes
        assert metadata["schema_checksum"] == backup_info.schema_checksum


class TestMigrationRegistry:
    """Test migration registry."""
    
    def test_migrations_registered(self):
        """Test that migrations are registered."""
        all_revisions = migration_registry.get_all_revisions()
        
        assert len(all_revisions) >= 2
        assert "001_initial" in all_revisions
        assert "002_legacy_data" in all_revisions
    
    def test_migration_order(self):
        """Test that migrations are ordered correctly."""
        order = migration_registry.get_migration_order()
        
        # 001 should come before 002
        assert order.index("001_initial") < order.index("002_legacy_data")
    
    def test_get_migration(self):
        """Test getting migration by revision."""
        spec = migration_registry.get_migration("001_initial")
        
        assert spec.revision == "001_initial"
        assert spec.name == "Initial V2 Canonical Schema"
        assert len(spec.dependencies) == 0
    
    def test_get_migration_functions(self):
        """Test getting migration upgrade/downgrade functions."""
        upgrade_fn = migration_registry.get_upgrade_function("001_initial")
        downgrade_fn = migration_registry.get_downgrade_function("001_initial")
        
        assert callable(upgrade_fn)
        assert callable(downgrade_fn)


class TestMigrationExecution:
    """Test migration execution."""
    
    def test_migration_001_upgrade(self, temp_db):
        """Test migration 001 upgrade."""
        engine, db_path = temp_db
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade
        
        with Session(engine) as session:
            upgrade(session)
        
        # Verify migration history table exists
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_history'"
            ))
            assert result.fetchone() is not None
        
        # Verify migration was recorded
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM migration_history WHERE revision='001_initial'"
            ))
            assert result.scalar() == 1
    
    def test_migration_001_downgrade(self, temp_db):
        """Test migration 001 downgrade."""
        engine, db_path = temp_db
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import (
            upgrade, downgrade
        )
        
        # First upgrade
        with Session(engine) as session:
            upgrade(session)
        
        # Then downgrade
        with Session(engine) as session:
            downgrade(session)
        
        # Verify tables were dropped
        with engine.connect() as conn:
            for table in ["chat_sessions", "v2_tasks", "execution_events"]:
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
                ), {"name": table})
                assert result.fetchone() is None
    
    def test_migration_002_upgrade_with_backend_data(self, temp_db_with_backend_tables):
        """Test migration 002 with backend data."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        # First run migration 001
        with Session(engine) as session:
            upgrade_001(session)
        
        # Insert test data into backend tables
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chat_sessions (id, title, status)
                VALUES ('session-1', 'Test Session', 'idle')
            """))
            conn.commit()
        
        # Run migration 002
        with Session(engine) as session:
            upgrade_002(session)
        
        # Verify data was migrated
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM chat_sessions"))
            assert result.scalar() == 1
    
    def test_data_integrity_preservation(self, temp_db_with_backend_tables):
        """Test that data integrity is preserved during migration."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        # Insert test data
        test_session_id = "test-session-123"
        test_task_id = "test-task-456"
        
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chat_sessions (id, title, status, created_at)
                VALUES (:id, 'Test Session', 'active', '2024-01-01T00:00:00')
            """), {"id": test_session_id})
            
            conn.execute(text("""
                INSERT INTO parent_tasks (id, conversation_id, title, status, created_at)
                VALUES (:id, :conversation_id, 'Test Task', 'pending', '2024-01-01T00:00:00')
            """), {"id": test_task_id, "conversation_id": test_session_id})
            
            conn.commit()
        
        # Run migrations
        with Session(engine) as session:
            upgrade_001(session)
        
        with Session(engine) as session:
            upgrade_002(session)
        
        # Verify IDs preserved
        with engine.connect() as conn:
            # Check session
            result = conn.execute(text("""
                SELECT id, title, status FROM chat_sessions WHERE id = :id
            """), {"id": test_session_id})
            row = result.fetchone()
            assert row is not None
            assert row[0] == test_session_id
            assert row[1] == "Test Session"
            assert row[2] == "active"
            
            # Check task
            result = conn.execute(text("""
                SELECT id, session_id, prompt FROM v2_tasks WHERE id = :id
            """), {"id": test_task_id})
            row = result.fetchone()
            assert row is not None
            assert row[0] == test_task_id
            assert row[1] == test_session_id


class TestDataIntegrityRequirements:
    """Test data integrity requirements from Phase 9 spec."""
    
    def test_row_count_preservation(self, temp_db_with_backend_tables):
        """Test that row counts are preserved during migration."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        # Insert test data
        with engine.connect() as conn:
            for i in range(5):
                conn.execute(text("""
                    INSERT INTO chat_sessions (id, title)
                    VALUES (:id, 'Session ' || :id)
                """), {"id": f"session-{i}"})
            conn.commit()
        
        # Get source count
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM chat_sessions"))
            source_count = result.scalar()
        
        # Run migrations
        with Session(engine) as session:
            upgrade_001(session)
        
        with Session(engine) as session:
            upgrade_002(session)
        
        # Get target count
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM chat_sessions"))
            target_count = result.scalar()
        
        assert source_count == target_count
    
    def test_id_preservation(self, temp_db_with_backend_tables):
        """Test that IDs are preserved during migration."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        test_id = "preserved-id-12345"
        
        # Insert test data
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chat_sessions (id, title)
                VALUES (:id, 'Test')
            """), {"id": test_id})
            conn.commit()
        
        # Run migrations
        with Session(engine) as session:
            upgrade_001(session)
        
        with Session(engine) as session:
            upgrade_002(session)
        
        # Verify ID preserved
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id FROM chat_sessions WHERE id = :id
            """), {"id": test_id})
            row = result.fetchone()
            assert row is not None
            assert row[0] == test_id
    
    def test_timestamp_preservation(self, temp_db_with_backend_tables):
        """Test that timestamps are preserved during migration."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        test_created_at = "2024-01-15T10:30:00"
        test_updated_at = "2024-01-15T11:45:00"
        
        # Insert test data
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chat_sessions (id, title, created_at, updated_at)
                VALUES ('timestamp-test', 'Test', :created_at, :updated_at)
            """), {"created_at": test_created_at, "updated_at": test_updated_at})
            conn.commit()
        
        # Run migrations
        with Session(engine) as session:
            upgrade_001(session)
        
        with Session(engine) as session:
            upgrade_002(session)
        
        # Verify timestamps preserved
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT created_at, updated_at FROM chat_sessions WHERE id = 'timestamp-test'
            """))
            row = result.fetchone()
            assert row is not None
            assert row[0] == test_created_at
            assert row[1] == test_updated_at
    
    def test_payload_hash_preservation(self, temp_db_with_backend_tables):
        """Test that JSON payload data integrity is preserved."""
        engine, db_path = temp_db_with_backend_tables
        
        from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002
        
        test_data = {"key": "value", "nested": {"a": 1, "b": 2}}
        test_json = json.dumps(test_data)
        
        # Insert test data
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chat_sessions (id, metadata_json)
                VALUES ('payload-test', :metadata_json)
            """), {"metadata_json": test_json})
            conn.commit()
        
        # Run migrations
        with Session(engine) as session:
            upgrade_001(session)
        
        with Session(engine) as session:
            upgrade_002(session)
        
        # Verify JSON preserved
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT metadata_json FROM chat_sessions WHERE id = 'payload-test'
            """))
            row = result.fetchone()
            assert row is not None
            assert row[0] == test_json
