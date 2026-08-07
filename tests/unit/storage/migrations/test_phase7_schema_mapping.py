"""Unit tests for Phase 7 — Schema Audit, Mapping & Preflight Validator."""

import json
import pytest
from sqlalchemy import create_engine, text

from windagent_storage.migrations.inventory import SchemaInventoryAnalyzer
from windagent_storage.migrations.mapping import (
    detect_self_copy_sql,
    TABLE_CLASSIFICATIONS,
    MigrationMappingRegistry,
)
from windagent_storage.migrations.preflight import (
    DataMigrationPreflightValidator,
    DuplicateRule,
    OrphanRule,
)


@pytest.fixture
def temp_legacy_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE legacy_chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                metadata_json TEXT,
                created_at TEXT
            );
        """))
        conn.execute(text("""
            INSERT INTO legacy_chat_sessions (id, title, metadata_json, created_at)
            VALUES ('s1', 'Session 1', '{"key": "val"}', '2026-01-01T00:00:00Z');
        """))
    yield engine
    engine.dispose()


def test_schema_inventory_analyzer(temp_legacy_db):
    analyzer = SchemaInventoryAnalyzer()
    snapshot = analyzer.snapshot_schema(temp_legacy_db)
    assert "legacy_chat_sessions" in snapshot["tables"]
    cols = [c["name"] for c in snapshot["tables"]["legacy_chat_sessions"]["columns"]]
    assert "id" in cols
    assert "metadata_json" in cols

    csv_report = analyzer.export_table_inventory_csv(temp_legacy_db)
    assert "legacy_chat_sessions" in csv_report


def test_detect_self_copy_sql():
    self_copy = "INSERT INTO chat_sessions (id, title) SELECT id, title FROM chat_sessions;"
    assert detect_self_copy_sql(self_copy) is True

    valid_copy = "INSERT INTO chat_sessions (id, title) SELECT id, title FROM legacy_chat_sessions_snapshot;"
    assert detect_self_copy_sql(valid_copy) is False


def test_table_classifications():
    assert TABLE_CLASSIFICATIONS["chat_sessions"] == "shared_name_incompatible"
    assert TABLE_CLASSIFICATIONS["execution_events"] == "shared_name_incompatible"
    assert TABLE_CLASSIFICATIONS["v2_tasks"] == "canonical_only"


def test_preflight_validator_pass(temp_legacy_db):
    validator = DataMigrationPreflightValidator()
    result = validator.validate(temp_legacy_db, required_tables=["legacy_chat_sessions"])
    assert result.is_valid is True
    assert result.verdict == "PASS"


def test_preflight_validator_fails_missing_table(temp_legacy_db):
    validator = DataMigrationPreflightValidator()
    result = validator.validate(temp_legacy_db, required_tables=["missing_table_xyz"])
    assert result.is_valid is False
    assert result.verdict == "BLOCKED_DATA_MIGRATION"
    assert any("missing_table_xyz" in err for err in result.errors)


def test_preflight_validator_fails_corrupt_json(temp_legacy_db):
    with temp_legacy_db.begin() as conn:
        conn.execute(text("""
            INSERT INTO legacy_chat_sessions (id, title, metadata_json, created_at)
            VALUES ('s-corrupt', 'Corrupt', '{"key": corrupt_json', '2026-01-01T00:00:00Z');
        """))

    validator = DataMigrationPreflightValidator()
    result = validator.validate(temp_legacy_db, required_tables=["legacy_chat_sessions"])
    assert result.is_valid is False
    assert result.verdict == "BLOCKED_DATA_MIGRATION"
    assert any("Invalid JSON" in err for err in result.errors)


@pytest.fixture
def dup_orphan_db():
    """A DB with a duplicated session key and an orphan conversation reference."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY,
                status TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE agent_instances (
                agent_instance_id TEXT PRIMARY KEY,
                conversation_id TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE agent_sessions (
                agent_session_id TEXT PRIMARY KEY,
                windagent_session_id TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE task_plan_versions (
                plan_version_id TEXT PRIMARY KEY,
                parent_task_id TEXT,
                version INTEGER
            );
        """))
        conn.execute(text(
            "INSERT INTO conversations (conversation_id, status) VALUES ('c1', 'idle')"
        ))
        # Valid instance row plus one orphan whose conversation does not exist.
        conn.execute(text(
            "INSERT INTO agent_instances (agent_instance_id, conversation_id) VALUES ('a1', 'c1')"
        ))
        conn.execute(text(
            "INSERT INTO agent_instances (agent_instance_id, conversation_id) VALUES ('a2', 'c-missing')"
        ))
        # Duplicate windagent_session_id.
        conn.execute(text(
            "INSERT INTO agent_sessions (agent_session_id, windagent_session_id) VALUES ('s1', 'ws-dup')"
        ))
        conn.execute(text(
            "INSERT INTO agent_sessions (agent_session_id, windagent_session_id) VALUES ('s2', 'ws-dup')"
        ))
        # Duplicate plan version for the same parent task.
        conn.execute(text(
            "INSERT INTO task_plan_versions (plan_version_id, parent_task_id, version) VALUES ('p1', 't1', 1)"
        ))
        conn.execute(text(
            "INSERT INTO task_plan_versions (plan_version_id, parent_task_id, version) VALUES ('p2', 't1', 1)"
        ))
    yield engine
    engine.dispose()


def test_preflight_detects_duplicate_session_keys(dup_orphan_db):
    validator = DataMigrationPreflightValidator()
    result = validator.validate(
        dup_orphan_db,
        duplicate_rules=[
            DuplicateRule("agent_sessions", "windagent_session_id"),
            DuplicateRule("task_plan_versions", "parent_task_id, version"),
        ],
    )
    assert result.is_valid is False
    assert result.verdict == "BLOCKED_DATA_MIGRATION"
    assert "agent_sessions.windagent_session_id" in result.duplicates
    assert "ws-dup" in result.duplicates["agent_sessions.windagent_session_id"]
    assert any("Duplicate" in err and "windagent_session_id" in err for err in result.errors)


def test_preflight_detects_orphan_conversation(dup_orphan_db):
    validator = DataMigrationPreflightValidator()
    result = validator.validate(
        dup_orphan_db,
        orphan_rules=[
            OrphanRule(
                child_table="agent_instances",
                child_column="conversation_id",
                parent_table="conversations",
                parent_column="conversation_id",
            ),
        ],
    )
    assert result.is_valid is False
    assert result.orphans["agent_instances.conversation_id"] == 1
    assert any("Orphan" in err and "agent_instances.conversation_id" in err for err in result.errors)


def test_preflight_clean_db_passes_duplicate_and_orphan_checks(dup_orphan_db):
    """With the anomaly rows removed, duplicate/orphan checks pass."""
    with dup_orphan_db.begin() as conn:
        conn.execute(text("DELETE FROM agent_sessions WHERE agent_session_id = 's2'"))
        conn.execute(text("DELETE FROM task_plan_versions WHERE plan_version_id = 'p2'"))
        conn.execute(text("DELETE FROM agent_instances WHERE agent_instance_id = 'a2'"))

    validator = DataMigrationPreflightValidator()
    result = validator.validate(
        dup_orphan_db,
        duplicate_rules=[
            DuplicateRule("agent_sessions", "windagent_session_id"),
            DuplicateRule("task_plan_versions", "parent_task_id, version"),
        ],
        orphan_rules=[
            OrphanRule(
                child_table="agent_instances",
                child_column="conversation_id",
                parent_table="conversations",
                parent_column="conversation_id",
            ),
        ],
    )
    assert result.is_valid is True
    assert result.verdict == "PASS"
    assert result.duplicates == {}
    assert result.orphans == {}
