"""Unit tests for Phase 9 — Rollback & Backup Restoration Rehearsal."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from windagent_storage.migrations.backup_manager import BackupManager
from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002


@pytest.fixture
def temp_db_file():
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / "test_legacy.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE legacy_chat_sessions_snapshot (
                id TEXT PRIMARY KEY,
                title TEXT,
                agent_id TEXT,
                workspace_root TEXT,
                created_at TEXT,
                updated_at TEXT,
                last_event_sequence INTEGER,
                metadata_json TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE parent_tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                conversation_id TEXT,
                status TEXT,
                label TEXT,
                created_at TEXT
            );
        """))
        conn.execute(text("""
            INSERT INTO legacy_chat_sessions_snapshot (id, title, created_at, updated_at, metadata_json)
            VALUES ('s-baseline-1', 'Baseline Session', '2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z', '{"baseline": true}');
        """))
        conn.execute(text("""
            INSERT INTO parent_tasks (id, title, conversation_id, status, label, created_at)
            VALUES ('t-baseline-1', 'Baseline Task', 's-baseline-1', 'completed', 'base', '2026-01-01T00:05:00Z');
        """))
        conn.commit()

    yield engine, db_path, tmp_dir
    engine.dispose()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_full_rollback_rehearsal_sequence(temp_db_file):
    """
    Rehearsal Sequence:
    legacy DB -> backup -> migrate 001&002 -> validate canonical -> restore backup -> validate legacy baseline -> re-migrate -> validate canonical second time.
    """
    engine, db_path, tmp_dir = temp_db_file
    backup_mgr = BackupManager(backup_root=tmp_dir / "backups")

    # 1. Create baseline backup
    backup_info = backup_mgr.create_backup(engine=engine, backup_id="baseline_rehearsal")
    assert backup_info.file_checksum != ""
    assert backup_info.row_counts["legacy_chat_sessions_snapshot"] == 1

    # 2. Run migration 001 & 002
    with Session(engine) as session:
        upgrade_001(session)
        upgrade_002(session)

    # 3. Validate canonical DB state
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chat_sessions")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_tasks")).scalar() == 1

    # 4. Restore backup to return to baseline
    restored = backup_mgr.restore_backup(backup_id="baseline_rehearsal", engine=engine)
    assert restored is True

    # 5. Validate legacy state restored to exact baseline
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM legacy_chat_sessions_snapshot")).scalar() == 1
        # Canonical table chat_sessions should not exist in baseline database
        res_cat = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='v2_tasks'")).fetchone()
        assert res_cat is None

    # 6. Re-run migration 001 & 002 second time
    with Session(engine) as session:
        upgrade_001(session)
        upgrade_002(session)

    # 7. Validate canonical DB state second time
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chat_sessions")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_tasks")).scalar() == 1


def test_tampered_backup_checksum_rejection(temp_db_file):
    """Corrupt/tampered backup archive is rejected by restore_backup with checksum mismatch."""
    engine, db_path, tmp_dir = temp_db_file
    backup_mgr = BackupManager(backup_root=tmp_dir / "backups")

    backup_info = backup_mgr.create_backup(engine=engine, backup_id="tampered_test")
    backup_file = Path(backup_info.backup_path)

    # Tamper with the backup file
    with open(backup_file, "ab") as f:
        f.write(b"CORRUPT_BYTES_INJECTED")

    # Restore must reject tampered file
    restored = backup_mgr.restore_backup(backup_id="tampered_test", engine=engine, verify_file_checksum=True)
    assert restored is False


def test_missing_backup_rejection(temp_db_file):
    engine, db_path, tmp_dir = temp_db_file
    backup_mgr = BackupManager(backup_root=tmp_dir / "backups")
    assert backup_mgr.restore_backup(backup_id="non_existent_id", engine=engine) is False
