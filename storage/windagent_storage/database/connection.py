"""
Database Connection Manager for WindAgent Architecture V2.
Configures async SQLAlchemy engine and session factories.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
import uuid
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool


class DatabaseManager:
    def __init__(
        self,
        db_url: str = "sqlite+aiosqlite:///windagent.db",
        echo: bool = False,
        release_telemetry: Any | None = None,
    ):
        self.db_url = db_url
        self.echo = echo
        self._release_telemetry = release_telemetry
        self.last_pre_migration_backup: Path | None = None

        # PostgreSQL needs pool configuration for asyncpg; SQLite uses appropriate pool
        if db_url.startswith("postgresql+asyncpg://") or db_url.startswith(
            "postgresql+psycopg2://"
        ):
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                pool_pre_ping=True,
            )
        elif db_url.startswith("sqlite+aiosqlite:///:memory:"):
            # In-memory SQLite needs StaticPool to share connection across sessions
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            # File-based SQLite: NullPool avoids "database is locked" on concurrent
            # writes; WAL + busy_timeout (G9.3) let parallel writers (fan-out DAG,
            # route locks, audit) proceed instead of failing with a lock error.
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                poolclass=NullPool,
            )

            @event.listens_for(self.engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _record) -> None:
                cur = dbapi_conn.cursor()
                try:
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA busy_timeout=30000")
                    cur.execute("PRAGMA synchronous=NORMAL")
                    # SQLite enforces FK constraints only when this pragma is
                    # enabled per-connection (GAP A / G1.2). Orphan inserts must
                    # be rejected at the DB boundary, not merely documented.
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.execute("PRAGMA cache_size=-64000")
                    cur.execute("PRAGMA temp_store=MEMORY")
                finally:
                    cur.close()

        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        if self._release_telemetry is not None:
            @event.listens_for(self.engine.sync_engine, "handle_error")
            def _record_database_lock_error(exception_context: Any) -> None:
                message = str(exception_context.original_exception).lower()
                if "database is locked" in message or "database schema is locked" in message:
                    self._release_telemetry.record_database_lock_error()

    async def create_tables(self, base_metadata: Any) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(base_metadata.create_all)

    def create_pre_migration_backup(self, backup_root: str | Path) -> Path | None:
        """Back up an existing file-backed SQLite DB before a release migration.

        The method returns ``None`` for a brand-new database because there is no
        existing state to preserve. PostgreSQL backups remain an infrastructure
        responsibility and are guarded by composition-level evidence checks.
        """
        prefix = "sqlite+aiosqlite:///"
        if not self.db_url.startswith(prefix):
            raise ValueError("automatic pre-migration backup supports only file-backed SQLite")
        source = Path(self.db_url[len(prefix) :]).resolve()
        if not source.exists() or source.name == ":memory:":
            return None
        from windagent_storage.migrations.release_rehearsal import create_sqlite_backup

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = (
            Path(backup_root).resolve()
            / f"pre-migration-{timestamp}-{uuid.uuid4().hex[:12]}.sqlite3"
        )
        self.last_pre_migration_backup = create_sqlite_backup(source, destination)
        return self.last_pre_migration_backup

    async def upgrade_to_head(self, base_metadata: Any) -> None:
        """Run the canonical Alembic migrations up to ``head``.

        Phase 1 — G1.1: replaces the runtime ``create_tables`` flow with a
        versioned, rollback-capable migration workflow for durable (file/DB)
        databases. In-memory SQLite cannot be migrated through a separate
        synchronous engine (each connection has its own private store), so it
        keeps the ``create_all`` fallback — in-memory DBs are test-only.
        """
        if self.db_url.startswith("sqlite+aiosqlite:///:memory:"):
            await self.create_tables(base_metadata)
            return

        from windagent_storage.migrations.runner import alembic_upgrade_head

        await asyncio.to_thread(alembic_upgrade_head, self.db_url)

    async def close(self) -> None:
        await self.engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
