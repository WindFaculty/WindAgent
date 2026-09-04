"""Canonical database engine and session factory for WindAgent V2.

PostgreSQL is the only V2 database outside isolated unit tests (plan
section 8).  The engine is therefore tuned for ``asyncpg`` pooling while a
non-canonical scheme is tolerated solely for hermetic test environments
configured through ``Settings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .unit_of_work import CheckpointHook, SqlUnitOfWork

if TYPE_CHECKING:
    from windagent.platform.configuration.settings import Environment, Settings

    from .contracts import UnitOfWork

CANONICAL_DIALECT_PREFIX = "postgresql"

DEFAULT_POOL_SIZE = 10
DEFAULT_MAX_OVERFLOW = 20
DEFAULT_POOL_TIMEOUT_S = 30.0
DEFAULT_POOL_RECYCLE_S = 1800.0


class NonCanonicalDatabaseError(RuntimeError):
    """Startup error raised when a non-PostgreSQL database is configured."""


class Database:
    """Owns one async engine plus the session factory derived from it.

    Instances are process-wide singletons in production composition roots.
    ``unit_of_work`` hands out independent transaction scopes that share the
    pool; every scope commits or rolls back on its own.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        url: str,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._url = make_url(url).render_as_string(hide_password=True)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        environment: Environment = "development",
        pool_size: int = DEFAULT_POOL_SIZE,
        max_overflow: int = DEFAULT_MAX_OVERFLOW,
        pool_timeout_s: float = DEFAULT_POOL_TIMEOUT_S,
        pool_recycle_s: float = DEFAULT_POOL_RECYCLE_S,
        echo: bool = False,
    ) -> Self:
        """Create the database from a raw URL.

        Outside the isolated test environment the URL must target the
        canonical engine; anything else fails at composition time instead of
        silently degrading production semantics (plan section 8).
        """
        _require_canonical_url(url, environment=environment)

        scheme = _scheme_of(url)
        if scheme.startswith(CANONICAL_DIALECT_PREFIX):
            engine = create_async_engine(
                url,
                echo=echo,
                pool_pre_ping=True,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout_s,
                pool_recycle=pool_recycle_s,
            )
        else:
            # Non-canonical engines only exist for hermetic isolated test
            # runs; a dedicated pool per connection keeps them hermetic.
            engine = create_async_engine(url, echo=echo, poolclass=NullPool)

        session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        return cls(engine, session_factory, url)

    @classmethod
    def from_settings(cls, settings: Settings, **options: Any) -> Self:
        """Create the database from application settings."""
        return cls.from_url(
            settings.database_url,
            environment=settings.environment,
            **options,
        )

    @property
    def engine(self) -> AsyncEngine:
        """The underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Factory for sessions that participate in unit-of-work scopes."""
        return self._session_factory

    @property
    def url(self) -> str:
        """Connection URL with credentials masked."""
        return self._url

    def unit_of_work(self, *, checkpoint_hook: CheckpointHook | None = None) -> UnitOfWork:
        """Return a fresh, independent transaction scope backed by the pool."""
        return SqlUnitOfWork(self._session_factory, checkpoint_hook=checkpoint_hook)

    async def dispose(self) -> None:
        """Close all pooled connections; the instance is unusable afterwards."""
        await self._engine.dispose()

    def __repr__(self) -> str:
        return f"Database({self._url})"


def _require_canonical_url(url: str, *, environment: Environment) -> None:
    if environment == "test":
        return
    scheme = _scheme_of(url)
    if not scheme.startswith(CANONICAL_DIALECT_PREFIX):
        raise NonCanonicalDatabaseError(
            "only PostgreSQL is a canonical WindAgent V2 database outside the "
            f"isolated test environment; got scheme {scheme!r}"
        )


def _scheme_of(url: str) -> str:
    return make_url(url).drivername.lower()
