"""
Phase 1 migration: durable routing authority schema.

Creates (idempotently):
- provider_routing_audit_v3
- ensures route_locks_v3 has version / reselection_reason / updated_at columns

Backfills:
- existing canonical models / endpoint bindings (reuses legacy backfill)
- no persisted route-lock snapshot exists at this commit, so nothing to migrate
  for locks (documented in rollback_receipt).

Rollback:
- drops provider_routing_audit_v3 (keeps data until explicitly purged)
- does NOT drop route_locks_v3 data; only the new columns are removed.

Idempotent: safe to re-run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from sqlalchemy import inspect, text

root_dir = Path(__file__).resolve().parents[3]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from windagent_storage.orm.models import BaseORM  # noqa: E402  (needs sys.path bootstrap above)
from windagent_storage.orm.v3_models import ProviderRoutingAuditV3ORM, RouteLockV3ORM  # noqa: E402


@dataclass
class Phase1MigrationReport:
    tables_created: List[str] = field(default_factory=list)
    columns_added: List[str] = field(default_factory=list)
    status: str = "PASSED"
    warnings: List[str] = field(default_factory=list)


def migrate(engine: Any) -> Phase1MigrationReport:
    """Idempotently apply Phase 1 routing authority schema.

    ``engine`` is a SYNCHRONOUS SQLAlchemy engine (see
    windagent_storage.database.sync_factory).
    """
    report = Phase1MigrationReport()
    inspector = inspect(engine)

    # 1. Create provider_routing_audit_v3 if missing
    existing_tables = set(inspector.get_table_names())
    if ProviderRoutingAuditV3ORM.__tablename__ not in existing_tables:
        BaseORM.metadata.create_all(engine, tables=[ProviderRoutingAuditV3ORM.__table__])
        report.tables_created.append(ProviderRoutingAuditV3ORM.__tablename__)

    # 2. Add new columns to route_locks_v3 if missing (SQLite safe)
    if RouteLockV3ORM.__tablename__ in existing_tables:
        cols = {c["name"] for c in inspector.get_columns(RouteLockV3ORM.__tablename__)}
        with engine.begin() as conn:
            if "version" not in cols:
                conn.execute(text("ALTER TABLE route_locks_v3 ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
                report.columns_added.append("route_locks_v3.version")
            if "reselection_reason" not in cols:
                conn.execute(text("ALTER TABLE route_locks_v3 ADD COLUMN reselection_reason VARCHAR(128)"))
                report.columns_added.append("route_locks_v3.reselection_reason")
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE route_locks_v3 ADD COLUMN updated_at DATETIME"))
                report.columns_added.append("route_locks_v3.updated_at")

        # 3. Partial unique index: at most ONE active lock per (scope_type, scope_id).
        existing_indexes = {ix["name"] for ix in inspector.get_indexes(RouteLockV3ORM.__tablename__)}
        if "uq_route_locks_v3_active_scope" not in existing_indexes:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX uq_route_locks_v3_active_scope "
                    "ON route_locks_v3 (scope_type, scope_id) WHERE status = 'active'"
                ))
            report.columns_added.append("index:uq_route_locks_v3_active_scope")

    return report


def rollback(engine: Any) -> Phase1MigrationReport:
    """Rollback Phase 1 schema additions.

    Keeps route_locks_v3 rows; only drops the audit table and the two optional
    columns. Data is preserved (not purged) per ban_ke_hoach.md §rollback.
    """
    report = Phase1MigrationReport()
    inspector = inspect(engine)

    existing_tables = set(inspector.get_table_names())
    if ProviderRoutingAuditV3ORM.__tablename__ in existing_tables:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {ProviderRoutingAuditV3ORM.__tablename__}"))
        report.tables_created.append(f"dropped:{ProviderRoutingAuditV3ORM.__tablename__}")

    if RouteLockV3ORM.__tablename__ in existing_tables:
        cols = {c["name"] for c in inspector.get_columns(RouteLockV3ORM.__tablename__)}
        existing_indexes = {ix["name"] for ix in inspector.get_indexes(RouteLockV3ORM.__tablename__)}
        with engine.begin() as conn:
            if "uq_route_locks_v3_active_scope" in existing_indexes:
                conn.execute(text("DROP INDEX IF EXISTS uq_route_locks_v3_active_scope"))
                report.columns_added.append("dropped:index:uq_route_locks_v3_active_scope")
            # SQLite cannot DROP COLUMN on old versions; wrap defensively.
            for col in ("version", "reselection_reason", "updated_at"):
                if col in cols:
                    try:
                        conn.execute(text(f"ALTER TABLE route_locks_v3 DROP COLUMN {col}"))
                        report.columns_added.append(f"dropped:route_locks_v3.{col}")
                    except Exception as exc:
                        report.warnings.append(f"Could not drop column {col}: {exc}")
    return report
