"""Unit tests for Phase 8 — Data Migration & Integrity Verification."""

import json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from windagent_storage.migrations.v2_canonical.migration_001_initial import upgrade as upgrade_001
from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade as upgrade_002, downgrade as downgrade_002


@pytest.fixture
def temp_db_with_legacy_tables():
    engine = create_engine("sqlite:///:memory:")
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
            CREATE TABLE workflows (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE workflow_steps (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                order_index INTEGER,
                name TEXT,
                tool_name TEXT,
                params_json TEXT,
                status TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE legacy_execution_events_snapshot (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                event_type TEXT,
                payload_json TEXT,
                event_seq INTEGER,
                created_at TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE task_artifacts (
                id TEXT PRIMARY KEY,
                artifact_type TEXT,
                path_or_uri TEXT,
                metadata_json TEXT,
                checksum TEXT,
                created_at TEXT
            );
        """))

        # Seed test data
        conn.execute(text("""
            INSERT INTO legacy_chat_sessions_snapshot (id, title, created_at, updated_at, metadata_json)
            VALUES ('s-1', 'Session One', '2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z', '{"key": "val1"}');
        """))
        conn.execute(text("""
            INSERT INTO parent_tasks (id, title, conversation_id, status, label, created_at)
            VALUES ('t-1', 'Task One', 's-1', 'completed', 'tag1', '2026-01-01T00:05:00Z');
        """))
        conn.execute(text("""
            INSERT INTO workflows (id, session_id, status, created_at, updated_at)
            VALUES ('wf-1', 's-1', 'completed', '2026-01-01T00:10:00Z', '2026-01-01T00:15:00Z');
        """))
        conn.execute(text("""
            INSERT INTO workflow_steps (id, workflow_id, order_index, name, tool_name, params_json, status)
            VALUES ('step-1', 'wf-1', 1, 'Step One', 'tool_a', '{"param": 1}', 'completed');
        """))
        conn.execute(text("""
            INSERT INTO legacy_execution_events_snapshot (id, session_id, event_type, payload_json, event_seq, created_at)
            VALUES ('evt-1', 's-1', 'StepExecuted', '{"result": "ok"}', 1, '2026-01-01T00:12:00Z');
        """))
        conn.execute(text("""
            INSERT INTO task_artifacts (id, artifact_type, path_or_uri, metadata_json, checksum, created_at)
            VALUES ('art-1', 'file', '/tmp/doc.txt', '{"size": 100}', 'abc123hash', '2026-01-01T00:14:00Z');
        """))
        conn.commit()

    yield engine
    engine.dispose()


def test_data_migration_002_success(temp_db_with_legacy_tables):
    engine = temp_db_with_legacy_tables

    with Session(engine) as session:
        upgrade_001(session)

    with Session(engine) as session:
        upgrade_002(session)

    with engine.connect() as conn:
        # Verify row counts
        assert conn.execute(text("SELECT COUNT(*) FROM chat_sessions")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_tasks")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_workflow_runs")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_workflow_steps")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM execution_events")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_artifacts")).scalar() == 1

        # Verify ID preservation
        s = conn.execute(text("SELECT id, title, metadata_json FROM chat_sessions WHERE id='s-1'")).fetchone()
        assert s is not None
        assert s.title == "Session One"
        assert json.loads(s.metadata_json)["key"] == "val1"

        t = conn.execute(text("SELECT prompt, session_id, status FROM v2_tasks WHERE id='t-1'")).fetchone()
        assert t is not None
        assert t.prompt == "Task One"
        assert t.session_id == "s-1"

        # Verify migration history record
        hist = conn.execute(text("SELECT status FROM migration_history WHERE revision='002_legacy_data'")).fetchone()
        assert hist is not None
        assert hist.status == "completed"


def test_data_migration_002_idempotent(temp_db_with_legacy_tables):
    engine = temp_db_with_legacy_tables

    with Session(engine) as session:
        upgrade_001(session)
        upgrade_002(session)

    # Second run should be idempotent
    with Session(engine) as session:
        upgrade_002(session)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chat_sessions")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM v2_tasks")).scalar() == 1


def test_data_migration_002_downgrade(temp_db_with_legacy_tables):
    engine = temp_db_with_legacy_tables

    with Session(engine) as session:
        upgrade_001(session)
        upgrade_002(session)
        downgrade_002(session)

    with engine.connect() as conn:
        hist = conn.execute(text("SELECT status, direction FROM migration_history WHERE revision='002_legacy_data'")).fetchone()
        assert hist is not None
        assert hist.direction == "downgrade"
        assert hist.status == "rolled_back"
