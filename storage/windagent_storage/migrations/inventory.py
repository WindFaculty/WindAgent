"""Schema Inventory Snapshot and Inspection Tooling (Phase 7)."""

from __future__ import annotations
import csv
import json
from io import StringIO
from typing import Any, Dict, List
from sqlalchemy import Engine, inspect


class SchemaInventoryAnalyzer:
    """Inspects database engines to produce schema snapshots and inventory reports."""

    def snapshot_schema(self, engine: Engine) -> Dict[str, Any]:
        inspector = inspect(engine)
        tables_snapshot: Dict[str, Any] = {}

        for table_name in inspector.get_table_names():
            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": str(col.get("default")) if col.get("default") is not None else None,
                }
                for col in inspector.get_columns(table_name)
            ]
            pks = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
            fks = [
                {
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns", []),
                }
                for fk in inspector.get_foreign_keys(table_name)
            ]
            indexes = [
                {
                    "name": idx.get("name"),
                    "column_names": idx.get("column_names", []),
                    "unique": idx.get("unique", False),
                }
                for idx in inspector.get_indexes(table_name)
            ]

            tables_snapshot[table_name] = {
                "columns": columns,
                "primary_keys": pks,
                "foreign_keys": fks,
                "indexes": indexes,
            }

        return {"tables": tables_snapshot}

    def export_table_inventory_csv(self, engine: Engine) -> str:
        inspector = inspect(engine)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["table_name", "column_count", "primary_key_count", "foreign_key_count"])

        for table in inspector.get_table_names():
            cols = inspector.get_columns(table)
            pks = inspector.get_pk_constraint(table).get("constrained_columns", [])
            fks = inspector.get_foreign_keys(table)
            writer.writerow([table, len(cols), len(pks), len(fks)])

        return output.getvalue()
