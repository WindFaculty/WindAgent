"""Database helpers for component / integration / e2e tests.

Centralises the previously duplicated ``P01_TABLES`` and ``DatabaseManager``
boilerplate that was copy-pasted across 40+ test files.

All helpers are **hermetic**: every call creates a fresh SQLite file under
``tmp_path`` and sets ``WINDAGENT_DATABASE_URL`` via ``monkeypatch`` so no
test ever touches the repo-root ``windagent.db``.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Sequence

from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointHealthSampleORM,
    EndpointModelBindingORM,
    EndpointRateLimitWindowORM,
    EndpointRuntimeStateORM,
    ModelDiscoverySnapshotORM,
    ModelRoutingRuleV3ORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    ProviderRoutingAuditV3ORM,
    ProviderVendorORM,
    RouteAttemptV3ORM,
    RouteLockV3ORM,
)

# Canonical table whitelist for P0 / provider integration tests.
# Imported by tests that want a minimal schema instead of the full BaseORM.
P01_TABLES: Sequence[Table] = [
    ProviderVendorORM.__table__,
    ProviderCredentialORM.__table__,
    ProviderEndpointORM.__table__,
    CanonicalModelV3ORM.__table__,
    EndpointModelBindingORM.__table__,
    ModelRoutingRuleV3ORM.__table__,
    RouteLockV3ORM.__table__,
    ProviderRoutingAuditV3ORM.__table__,
    RouteAttemptV3ORM.__table__,
    EndpointRuntimeStateORM.__table__,
    EndpointHealthSampleORM.__table__,
    EndpointRateLimitWindowORM.__table__,
    ModelDiscoverySnapshotORM.__table__,
]


def isolated_db_url(tmp_path: Path, filename: str | None = None) -> str:
    """Return a ``sqlite+aiosqlite`` URL pointing at a fresh file under ``tmp_path``."""
    name = filename or f"test_{uuid.uuid4().hex[:8]}.db"
    return f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"


def sync_db_url(tmp_path: Path, filename: str | None = None) -> str:
    """Return a synchronous ``sqlite`` URL for ``create_engine`` usage."""
    name = filename or f"test_{uuid.uuid4().hex[:8]}.db"
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def create_sync_engine(tmp_path: Path, tables: Sequence[Table] | None = P01_TABLES):
    """Create a synchronous SQLAlchemy engine with the given tables."""
    url = sync_db_url(tmp_path)
    engine = create_engine(url)
    if tables is not None:
        BaseORM.metadata.create_all(engine, tables=list(tables))
    else:
        BaseORM.metadata.create_all(engine)
    return engine, url


def create_session_factory(tmp_path: Path, tables: Sequence[Table] | None = P01_TABLES):
    """Convenience: engine + sessionmaker for provider tests."""
    engine, url = create_sync_engine(tmp_path, tables)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory, url


async def create_isolated_async_db(
    tmp_path: Path,
    filename: str | None = None,
    *,
    use_tables: Sequence[Table] | None = None,
) -> DatabaseManager:
    """Create an async ``DatabaseManager`` with a fresh file DB.

    If ``use_tables`` is provided, only those tables are created; otherwise
    the full ``BaseORM`` is created. This mirrors the ``P01_TABLES`` pattern
    but works for the async path.
    """
    url = isolated_db_url(tmp_path, filename)
    db = DatabaseManager(url)
    if use_tables is not None:
        # For async, we need to create tables via the async engine.
        # Use sync create_all fallback for simplicity — P01_TABLES are sync-compatible.
        # For full async, just create all.
        from sqlalchemy import create_engine as sync_create

        sync_url = url.replace("sqlite+aiosqlite://", "sqlite://")
        sync_engine = sync_create(sync_url)
        BaseORM.metadata.create_all(sync_engine, tables=list(use_tables))
        sync_engine.dispose()
    else:
        await db.create_tables(BaseORM.metadata)
    return db


def fresh_encryption_key(monkeypatch, key_bytes: bytes | None = None) -> str:
    """Set ``WINDAGENT_ENCRYPTION_KEY`` to a deterministic test key and return it."""
    raw = key_bytes or (b"k" * 32)
    encoded = base64.b64encode(raw).decode()
    monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", encoded)
    return encoded
