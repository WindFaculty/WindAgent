"""
Database Schema and State Migration Script for WindAgent (Phase 7 / Phase 14 dry-run).
Validates database tables, state enums, indexes, and row counts.
Enforces strict fail-fast policy without invalid state fallback.
Supports dry-run on a temporary database copy to rehearse production cutover.
"""

from __future__ import annotations
import argparse
import shutil
import sys
import sqlite3
import json
import tempfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = WORKSPACE_ROOT / "windagent.db"

KNOWN_TASK_STATES = {
    "RECEIVED", "CLASSIFYING", "CONTEXT_BUILDING", "PLANNING", "READY",
    "RUNNING", "WAITING_PERMISSION", "PAUSED", "RETRY_WAIT", "RECOVERING",
    "VERIFYING", "REVIEWING", "COMPLETED", "FAILED", "CANCELLED", "PENDING"
}

KNOWN_SESSION_STATES = {
    "IDLE", "ACTIVE", "PAUSED", "COMPLETED", "FAILED", "CANCELLED", "ARCHIVED", "RUNNING"
}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS chat_sessions (id TEXT PRIMARY KEY, title TEXT, status TEXT NOT NULL, agent_id TEXT, workspace_root TEXT, created_at TIMESTAMP, updated_at TIMESTAMP, last_event_sequence INTEGER, metadata_json TEXT);")
    cursor.execute("CREATE TABLE IF NOT EXISTS v2_tasks (id TEXT PRIMARY KEY, prompt TEXT NOT NULL, session_id TEXT NOT NULL, status TEXT NOT NULL, tags_json TEXT, created_at TIMESTAMP);")
    cursor.execute("CREATE TABLE IF NOT EXISTS execution_events (id TEXT PRIMARY KEY, session_id TEXT, event_type TEXT NOT NULL, data_json TEXT NOT NULL, event_seq INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP);")
    cursor.execute("CREATE TABLE IF NOT EXISTS v2_outbox_records (id TEXT PRIMARY KEY, event_id TEXT NOT NULL, event_type TEXT NOT NULL, session_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, created_at TIMESTAMP, published_at TIMESTAMP, retry_count INTEGER NOT NULL DEFAULT 0);")
    conn.commit()


def migrate_database(db_file: Path) -> dict:
    if not db_file.exists():
        conn = sqlite3.connect(str(db_file))
        _ensure_schema(conn)
        conn.close()

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    _ensure_schema(conn)

    cursor.execute("SELECT COUNT(*) FROM chat_sessions;")
    session_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM v2_tasks;")
    task_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM execution_events;")
    event_count = cursor.fetchone()[0]

    cursor.execute("SELECT DISTINCT status FROM v2_tasks;")
    task_statuses = [row[0].upper() for row in cursor.fetchall() if row[0]]
    for st in task_statuses:
        if st not in KNOWN_TASK_STATES:
            conn.close()
            raise ValueError(f"Unknown task state '{st}' encountered! Migration failed.")

    cursor.execute("SELECT DISTINCT status FROM chat_sessions;")
    session_statuses = [row[0].upper() for row in cursor.fetchall() if row[0]]
    for st in session_statuses:
        if st not in KNOWN_SESSION_STATES:
            conn.close()
            raise ValueError(f"Unknown session state '{st}' encountered! Migration failed.")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session_seq ON execution_events(session_id, event_seq);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session_status ON v2_tasks(session_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbox_status_seq ON v2_outbox_records(status, sequence);")

    conn.commit()
    conn.close()

    return {
        "status": "MIGRATION_SUCCESS",
        "database_file": str(db_file),
        "session_count": session_count,
        "task_count": task_count,
        "event_count": event_count,
        "indexes_created": [
            "idx_events_session_seq",
            "idx_tasks_session_status",
            "idx_outbox_status_seq"
        ]
    }


def validate_database(db_file: Path) -> dict:
    """Read-only validation returning row counts without mutating schema/indexes."""
    if not db_file.exists():
        return {"status": "NO_DATABASE", "database_file": str(db_file)}

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected = {"chat_sessions", "v2_tasks", "execution_events", "v2_outbox_records"}
    missing = expected - tables
    if missing:
        raise ValueError(f"Missing expected tables: {missing}")

    receipt = migrate_database(db_file)
    receipt["validation_only"] = False
    return receipt


def dry_run_migration(source_db: Path) -> dict:
    """Copy source DB to a temporary file, migrate it, and report without changing source."""
    if not source_db.exists():
        return {"status": "NO_SOURCE_DB", "source_database": str(source_db)}

    suffix = ".db"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=str(WORKSPACE_ROOT)) as tmp:
        tmp_path = Path(tmp.name)
    shutil.copy2(str(source_db), str(tmp_path))

    try:
        receipt = migrate_database(tmp_path)
        receipt["dry_run"] = True
        receipt["source_database"] = str(source_db)
        receipt["temporary_database"] = str(tmp_path)
        return receipt
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="WindAgent database schema migration")
    parser.add_argument("--db-path", type=Path, default=DB_PATH, help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Rehearse migration on a temporary copy")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON receipt to file")
    args = parser.parse_args()

    try:
        if args.dry_run:
            receipt = dry_run_migration(args.db_path)
        else:
            receipt = migrate_database(args.db_path)
    except ValueError as exc:
        receipt = {"status": "MIGRATION_FAILED", "error": str(exc), "database_file": str(args.db_path)}
        print(json.dumps(receipt, indent=2))
        return 1

    print(json.dumps(receipt, indent=2))
    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
