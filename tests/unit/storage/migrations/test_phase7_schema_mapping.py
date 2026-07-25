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
from windagent_storage.migrations.preflight import DataMigrationPreflightValidator


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
