"""
Synchronous session factory for the routing authority (Phase 1).

The application DB layer is async (``DatabaseManager``).  The routing
repositories (``v3_routing_repositories``) use a synchronous SQLAlchemy
``Session`` for short single-transaction writes.  This helper derives a sync
engine + sessionmaker from the same ``db_url`` the async layer uses, so API and
Worker share one durable store.

SQLite:  sqlite+aiosqlite:///x.db  ->  sqlite:///x.db
PostgreSQL: postgresql+asyncpg://  ->  postgresql+psycopg2://  (requires psycopg2)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def sync_db_url(db_url: str) -> str:
    """Map an async SQLAlchemy URL to its synchronous driver equivalent."""
    if db_url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + db_url[len("sqlite+aiosqlite://"):]
    if db_url.startswith("sqlite://"):
        return db_url
    if db_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + db_url[len("postgresql+asyncpg://"):]
    # Already sync or unknown — return as-is.
    return db_url


def make_sync_session_factory(db_url: str, echo: bool = False) -> sessionmaker[Session]:
    """Create a sync sessionmaker bound to the synchronous engine for ``db_url``."""
    sync_url = sync_db_url(db_url)
    engine_kwargs: Dict[str, Any] = {"echo": echo, "future": True}
    if sync_url.startswith("sqlite"):
        # ponytail: SQLite needs a busy timeout + WAL so concurrent routing
        # writes (lock + audit) don't raise "database is locked". NullPool opens
        # a fresh connection per checkout — cheap for SQLite, avoids QueuePool
        # exhaustion under thread-burst tests. Upgrade path: real backend pools.
        from sqlalchemy.pool import NullPool

        engine_kwargs["connect_args"] = {"timeout": 30}
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs["pool_size"] = 20
        engine_kwargs["max_overflow"] = 40
        engine_kwargs["pool_timeout"] = 60
    engine = create_engine(sync_url, **engine_kwargs)
    if sync_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
            finally:
                cur.close()

    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def sync_session(db_url: str) -> Iterator[Session]:
    """One-shot sync session context manager (tests / scripts)."""
    factory = make_sync_session_factory(db_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
