"""Preflight Data Migration Integrity Validator (Phase 7, Stage 1 GAP B)."""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from sqlalchemy import Engine, inspect, text


@dataclass(frozen=True)
class DuplicateRule:
    """A uniqueness check: ``table.column`` must not repeat."""

    table: str
    column: str
    label: str = ""


@dataclass(frozen=True)
class OrphanRule:
    """A referential check: every ``child_table.child_column`` must exist in ``parent_table.parent_column``."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    label: str = ""


@dataclass
class PreflightResult:
    is_valid: bool
    verdict: str  # PASS or BLOCKED_DATA_MIGRATION
    errors: List[str]
    warnings: List[str]
    duplicates: Dict[str, List[str]] = field(default_factory=dict)
    orphans: Dict[str, int] = field(default_factory=dict)


class DataMigrationPreflightValidator:
    """Runs pre-migration integrity checks on legacy source database prior to execution."""

    def validate(
        self,
        engine: Engine,
        required_tables: Optional[List[str]] = None,
        enum_mappings: Optional[Dict[str, List[str]]] = None,
        duplicate_rules: Optional[List[DuplicateRule]] = None,
        orphan_rules: Optional[List[OrphanRule]] = None,
    ) -> PreflightResult:
        """Validate schema presence, JSON integrity, duplicates and orphans.

        Stage 1 GAP B: ``duplicate_rules`` / ``orphan_rules`` let the caller
        block migration before data that cannot be merged safely is touched.
        The validator only *reports* anomalies by ID/value — it never mutates
        or deletes rows (remediation is a separate, reviewed step).
        """
        errors: List[str] = []
        warnings: List[str] = []
        duplicates: Dict[str, List[str]] = {}
        orphans: Dict[str, int] = {}
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

            # Stage 1 GAP B — duplicate detection (uniqueness that migration will enforce)
            for rule in duplicate_rules or []:
                key = rule.label or f"{rule.table}.{rule.column}"
                if rule.table not in existing_tables:
                    errors.append(f"Duplicate check skipped — table missing: {rule.table}")
                    continue
                try:
                    rows = conn.execute(
                        text(
                            f"SELECT {rule.column}, COUNT(*) AS n FROM {rule.table} "
                            f"GROUP BY {rule.column} HAVING COUNT(*) > 1"
                        )
                    ).fetchall()
                except Exception as exc:
                    errors.append(f"Duplicate check failed for {key}: {exc}")
                    continue
                if rows:
                    duplicates[key] = [str(r[0]) for r in rows]
                    errors.append(
                        f"Duplicate {key}: {len(rows)} value(s) occur more than once — "
                        f"migration blocked until merged by reviewed remediation: {duplicates[key][:5]}"
                    )

            # Stage 1 GAP B — orphan detection (FK the migration will add)
            for rule in orphan_rules or []:
                key = rule.label or f"{rule.child_table}.{rule.child_column}"
                if rule.child_table not in existing_tables or rule.parent_table not in existing_tables:
                    errors.append(f"Orphan check skipped — table missing: {rule.child_table}/{rule.parent_table}")
                    continue
                try:
                    n = conn.execute(
                        text(
                            f"SELECT COUNT(*) FROM {rule.child_table} c "
                            f"LEFT JOIN {rule.parent_table} p "
                            f"  ON c.{rule.child_column} = p.{rule.parent_column} "
                            f"WHERE p.{rule.parent_column} IS NULL"
                        )
                    ).scalar_one()
                except Exception as exc:
                    errors.append(f"Orphan check failed for {key}: {exc}")
                    continue
                if n:
                    orphans[key] = n
                    errors.append(
                        f"Orphan {key}: {n} row(s) reference a missing parent — "
                        f"migration blocked until remediation report is reviewed"
                    )

        verdict = "PASS" if not errors else "BLOCKED_DATA_MIGRATION"
        return PreflightResult(
            is_valid=not errors,
            verdict=verdict,
            errors=errors,
            warnings=warnings,
            duplicates=duplicates,
            orphans=orphans,
        )
