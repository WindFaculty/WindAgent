"""Source-to-Target Schema Mapping and Self-Copy SQL Guard (Phase 7)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


TABLE_CLASSIFICATIONS = {
    "chat_sessions": "shared_name_incompatible",
    "execution_events": "shared_name_incompatible",
    "v2_tasks": "canonical_only",
    "outbox_records": "canonical_only",
    "outbox_replay_audit": "canonical_only",
    "legacy_sessions": "legacy_only",
    "legacy_events": "legacy_only",
}


@dataclass
class ColumnMapping:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    transformation: str = "direct_copy"
    null_policy: str = "allow_null"
    enum_mapping: Optional[Dict[str, str]] = None
    default_policy: Optional[str] = None
    validation_rule: Optional[str] = None
    rollback_strategy: str = "drop_target_table"


def detect_self_copy_sql(sql_statement: str) -> bool:
    """Detect forbidden self-copy SQL patterns (INSERT INTO x SELECT ... FROM x)."""
    clean_sql = " ".join(sql_statement.upper().split())
    if "INSERT INTO" in clean_sql and "SELECT" in clean_sql and "FROM" in clean_sql:
        try:
            parts_into = clean_sql.split("INSERT INTO")[1].strip().split()
            target_table = parts_into[0].strip("(`\"'")
            parts_from = clean_sql.split("FROM")[1].strip().split()
            source_table = parts_from[0].strip("(`\"';")
            if target_table == source_table:
                return True
        except Exception:
            pass
    return False


class MigrationMappingRegistry:
    """Maintains source-to-target table and column mappings for legacy to canonical migration."""

    def __init__(self):
        self._mappings: List[ColumnMapping] = []
        self._init_default_mappings()

    def _init_default_mappings(self):
        # Chat sessions mapping
        self._mappings.extend([
            ColumnMapping("legacy_chat_sessions_snapshot", "id", "chat_sessions", "id", null_policy="fail_on_null"),
            ColumnMapping("legacy_chat_sessions_snapshot", "title", "chat_sessions", "title"),
            ColumnMapping("legacy_chat_sessions_snapshot", "created_at", "chat_sessions", "created_at"),
            ColumnMapping("legacy_chat_sessions_snapshot", "updated_at", "chat_sessions", "updated_at"),
            ColumnMapping("legacy_chat_sessions_snapshot", "metadata_json", "chat_sessions", "metadata_json"),
        ])

    def get_mappings_for_target(self, target_table: str) -> List[ColumnMapping]:
        return [m for m in self._mappings if m.target_table == target_table]
