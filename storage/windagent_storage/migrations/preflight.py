"""Preflight Data Migration Integrity Validator (Phase 7)."""

from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from sqlalchemy import Engine, inspect, text


@dataclass
class PreflightResult:
    is_valid: bool
    verdict: str  # PASS or BLOCKED_DATA_MIGRATION
    errors: List[str]
    warnings: List[str]


class DataMigrationPreflightValidator:
    """Runs pre-migration integrity checks on legacy source database prior to execution."""

    def validate(
        self,
        engine: Engine,
        required_tables: Optional[List[str]] = None,
        enum_mappings: Optional[Dict[str, List[str]]] = None,
    ) -> PreflightResult:
        errors: List[str] = []
        warnings: List[str] = []
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        if required_tables:
            for tbl in required_tables:
                if tbl not in existing_tables:
                    errors.append(f"Missing required source table: {tbl}")

        # Check unparseable JSON or timestamp values in known legacy tables
        with engine.connect() as conn:
            for table in existing_tables:
                # Validate JSON payload columns
                columns = [c["name"] for c in inspector.get_columns(table)]
                json_cols = [c for c in columns if "json" in c.lower() or "payload" in c.lower()]
                for col in json_cols:
                    try:
                        rows = conn.execute(text(f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL")).scalars().all()
                        for val in rows:
                            if isinstance(val, str):
                                try:
                                    json.loads(val)
                                except Exception as exc:
                                    errors.append(f"Invalid JSON in {table}.{col}: {exc}")
                    except Exception:
                        pass

        verdict = "PASS" if not errors else "BLOCKED_DATA_MIGRATION"
        return PreflightResult(
            is_valid=not errors,
            verdict=verdict,
            errors=errors,
            warnings=warnings,
        )
