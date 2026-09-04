"""Concrete SQL unit of work implementing the platform persistence contract.

Preserved semantics from the old storage layer: the scope opens one session,
binds session-scoped repositories at entry, commits or rolls back atomically,
and exposes a crash-gate checkpoint seam so higher layers (transactional
finalization, outbox writes) can inject test hooks at exact points without
production overhead.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import TracebackType
from typing import Any, Literal, Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .contracts import UnitOfWork

type CheckpointHook = Callable[[str], object]
"""Hook invoked at named checkpoints; may be sync or return an awaitable."""

CHECKPOINT_BEFORE_COMMIT = "before_commit"
CHECKPOINT_BEFORE_ROLLBACK = "before_rollback"

type RepositoryFactory = Callable[[AsyncSession], object]


class UnitOfWorkStateError(RuntimeError):
    """Raised when a unit of work is used against its lifecycle rules."""


class UnitOfWorkNotActiveError(UnitOfWorkStateError):
    """Raised when a unit of work is accessed outside its ``async with`` scope."""


class SqlUnitOfWork(UnitOfWork):
    """Session-backed transaction scope with repository composition.

    Repositories are registered as session-bound factories before entry and
    instantiated exactly once when the scope opens.  This keeps construction
    inside the persistence layer — the single allowlisted point for concrete
    adapters — exactly like the old ``SqlUnitOfWork`` composition seam.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        checkpoint_hook: CheckpointHook | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._checkpoint_hook = checkpoint_hook
        self._session: AsyncSession | None = None
        self._repository_factories: dict[str, RepositoryFactory] = {}
        self._repositories: dict[str, object] = {}

    def register_repository(self, name: str, factory: RepositoryFactory) -> Self:
        """Register a session-bound repository factory under ``name``."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("repository name must be non-empty text")
        if not callable(factory):
            raise TypeError("repository factory must be callable")
        if self._session is not None:
            raise UnitOfWorkStateError(
                "repositories must be registered before the scope is entered"
            )
        if name in self._repository_factories:
            raise ValueError(f"repository {name!r} is already registered")
        self._repository_factories[name] = factory
        return self

    def repository(self, name: str) -> Any:
        """Return the repository bound under ``name`` for this scope.

        Callers narrow the result to their own repository protocol; the unit
        of work stays domain-agnostic.
        """
        self._require_active()
        if name not in self._repositories:
            raise KeyError(f"no repository registered under {name!r}")
        return self._repositories[name]

    @property
    def session(self) -> AsyncSession:
        """The active session; raises outside the ``async with`` scope."""
        self._require_active()
        assert self._session is not None
        return self._session

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise UnitOfWorkStateError("unit of work is already active")
        session = self._session_factory()
        # SQLAlchemy autobegin mirrors the old scope exactly: the database
        # transaction starts with the first statement, and commit/rollback
        # are explicit.
        self._session = session
        self._repositories = {
            name: factory(session)
            for name, factory in self._repository_factories.items()
        }
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        session = self._session
        self._repositories = {}
        if session is not None:
            try:
                # Exception paths always roll back; a clean exit with an
                # abandoned open transaction discards it rather than
                # committing half-finished work.
                if exc_type is not None or session.in_transaction():
                    await session.rollback()
            finally:
                self._session = None
                await session.close()
        return False

    async def commit(self) -> None:
        """Atomically persist all work accumulated in this scope."""
        session = self._require_active()
        await self.checkpoint(CHECKPOINT_BEFORE_COMMIT)
        await session.commit()

    async def rollback(self) -> None:
        """Discard all work accumulated in this scope."""
        session = self._require_active()
        await self.checkpoint(CHECKPOINT_BEFORE_ROLLBACK)
        await session.rollback()

    async def checkpoint(self, name: str) -> None:
        """Invoke the crash-gate hook at ``name``.

        With no hook configured this is a strict no-op (zero overhead,
        identical to the old Phase 5A default).  A configured hook may be
        synchronous or asynchronous; both shapes are awaited/handled here.
        """
        hook = self._checkpoint_hook
        if hook is None:
            return
        outcome = hook(name)
        if inspect.isawaitable(outcome):
            await outcome

    def _require_active(self) -> AsyncSession:
        session = self._session
        if session is None:
            raise UnitOfWorkNotActiveError(
                "unit of work context is not active; enter it with "
                "'async with' first"
            )
        return session
