"""Non-destructive migration rehearsal for a SQLite production copy.

The source database is opened only as the input to SQLite's backup API.  All
upgrade, downgrade, and restore operations occur below ``backup_root``.  A live
database is never downgraded by this module: application rollback keeps the
additive schema and is allowed only after this rehearsal succeeds.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from windagent_storage.migrations.runner import (
    alembic_downgrade_base,
    alembic_upgrade_head,
)


IMMUTABLE_AUDIT_TABLES = (
    "task_plan_versions",
    "task_nodes",
    "task_edges",
    "conversation_events",
    "agent_turns",
    "route_attempts_v3",
    "partial_stream_artifacts",
)

# These tables form the existing read path that must remain usable while an
# older application binary is brought back against an additive newer schema.
DUAL_READ_REQUIRED_TABLES = (
    "conversations",
    "parent_tasks",
    "agent_instances",
    "agent_sessions",
    "task_plan_versions",
    "task_nodes",
    "task_edges",
    "task_node_runs",
    "tool_executions",
    "worktrees",
    "conversation_events",
)


@dataclass(frozen=True)
class TableDigest:
    table_name: str
    row_count: int
    digest: str


@dataclass(frozen=True)
class ReleaseRehearsalReceipt:
    source_database: Path
    backup_database: Path
    upgrade_copy: Path
    downgrade_copy: Path
    backup_sha256: str
    immutable_digests: tuple[TableDigest, ...]
    immutable_data_preserved: bool
    dual_read_compatible: bool
    downgrade_rehearsed_on_copy: bool
    restore_verified: bool
    application_rollback_allowed: bool
    database_downgrade_prohibited: bool = True


class ApplicationRollbackBlocked(RuntimeError):
    """Raised when a release lacks evidence for an application-only rollback."""


def create_sqlite_backup(source_database: str | Path, destination: str | Path) -> Path:
    """Create a consistent SQLite backup, including committed WAL contents."""
    source = _require_sqlite_file(source_database)
    target = Path(destination).resolve()
    if target == source:
        raise ValueError("backup destination must not be the source database")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as read_connection:
        with sqlite3.connect(target) as write_connection:
            read_connection.backup(write_connection)
    return target


def rehearse_sqlite_release(
    source_database: str | Path,
    backup_root: str | Path,
) -> ReleaseRehearsalReceipt:
    """Back up, upgrade, downgrade, and restore a production *copy*.

    The base downgrade intentionally destroys data in ``downgrade_copy``; it is
    exercised only to prove the migration path is executable.  The backup is
    restored immediately afterwards and immutable-plan/audit fingerprints must
    match before application rollback is marked safe.
    """
    source = _require_sqlite_file(source_database)
    rehearsal_dir = Path(backup_root).resolve() / f"phase9-{uuid.uuid4().hex}"
    rehearsal_dir.mkdir(parents=True, exist_ok=False)

    backup = create_sqlite_backup(source, rehearsal_dir / "source-backup.sqlite3")
    source_digests = _immutable_digests(backup)
    backup_hash = _sha256(backup)

    upgrade_copy = rehearsal_dir / "upgrade-copy.sqlite3"
    _copy_database(backup, upgrade_copy)
    alembic_upgrade_head(_sqlite_url(upgrade_copy))
    immutable_data_preserved = _immutable_digests(upgrade_copy, source_digests) == source_digests
    dual_read_compatible = set(DUAL_READ_REQUIRED_TABLES).issubset(
        _table_names(upgrade_copy)
    )

    downgrade_copy = rehearsal_dir / "downgrade-copy.sqlite3"
    _copy_database(backup, downgrade_copy)
    alembic_upgrade_head(_sqlite_url(downgrade_copy))
    alembic_downgrade_base(_sqlite_url(downgrade_copy))
    _copy_database(backup, downgrade_copy)
    restore_verified = _immutable_digests(downgrade_copy, source_digests) == source_digests

    allowed = immutable_data_preserved and dual_read_compatible and restore_verified
    return ReleaseRehearsalReceipt(
        source_database=source,
        backup_database=backup,
        upgrade_copy=upgrade_copy,
        downgrade_copy=downgrade_copy,
        backup_sha256=backup_hash,
        immutable_digests=source_digests,
        immutable_data_preserved=immutable_data_preserved,
        dual_read_compatible=dual_read_compatible,
        downgrade_rehearsed_on_copy=True,
        restore_verified=restore_verified,
        application_rollback_allowed=allowed,
    )


def require_application_only_rollback(receipt: ReleaseRehearsalReceipt) -> None:
    """Guard a binary rollback; never authorise a live schema downgrade."""
    if not receipt.application_rollback_allowed:
        raise ApplicationRollbackBlocked(
            "application rollback is blocked until backup, dual-read, and immutable-data "
            "rehearsal checks pass"
        )
    if not receipt.database_downgrade_prohibited:
        raise ApplicationRollbackBlocked("live database downgrade must remain prohibited")


def _require_sqlite_file(database: str | Path) -> Path:
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError(f"SQLite database does not exist: {path}")
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA schema_version").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"not a readable SQLite database: {path}") from exc
    return path


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        destination.unlink()
    shutil.copy2(source, destination)


def _immutable_digests(
    database: Path, expected: tuple[TableDigest, ...] | None = None
) -> tuple[TableDigest, ...]:
    table_names = _table_names(database)
    requested = (
        tuple(item.table_name for item in expected)
        if expected is not None
        else tuple(table for table in IMMUTABLE_AUDIT_TABLES if table in table_names)
    )
    digests: list[TableDigest] = []
    with sqlite3.connect(database) as connection:
        for table in requested:
            if table not in table_names:
                return ()
            rows = connection.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            ).fetchall()
            hasher = hashlib.sha256()
            for row in rows:
                hasher.update(repr(tuple(row)).encode("utf-8"))
                hasher.update(b"\n")
            digests.append(TableDigest(table, len(rows), hasher.hexdigest()))
    return tuple(digests)


def _table_names(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()
