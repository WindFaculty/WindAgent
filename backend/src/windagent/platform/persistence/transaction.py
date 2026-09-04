"""Explicit transaction primitives over an async SQLAlchemy connection.

The old system's rule is preserved: a transaction scope owns its boundary,
commits only when the caller says so, and discards uncommitted work instead
of silently committing it.
"""

from __future__ import annotations

from enum import StrEnum
from types import TracebackType
from typing import Literal, Self

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncTransaction


class IsolationLevel(StrEnum):
    """Standard SQL isolation levels accepted by the canonical engine."""

    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


class TransactionOutcome(StrEnum):
    """Terminal state of a transaction scope."""

    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class TransactionScopeError(RuntimeError):
    """Raised when a transaction scope is used against its lifecycle rules."""


class TransactionScope:
    """An explicit, non-nested transaction boundary on one connection.

    ``commit`` and ``rollback`` are always explicit.  Leaving the context
    without committing rolls the transaction back — uncommitted work is
    never promoted to durable state by accident.
    """

    def __init__(
        self,
        connection: AsyncConnection,
        *,
        isolation_level: IsolationLevel | None = None,
    ) -> None:
        self._connection = connection
        self._isolation_level = isolation_level
        self._transaction: AsyncTransaction | None = None
        self._outcome = TransactionOutcome.ACTIVE

    @property
    def connection(self) -> AsyncConnection:
        """The connection the scope runs on."""
        return self._connection

    @property
    def outcome(self) -> TransactionOutcome:
        """Current lifecycle state of the scope."""
        return self._outcome

    async def __aenter__(self) -> Self:
        if self._transaction is not None:
            raise TransactionScopeError("transaction scope is already active")
        if self._connection.in_transaction():
            raise TransactionScopeError(
                "connection already has an active transaction; a scope must own "
                "its transaction boundary"
            )
        if self._isolation_level is not None:
            self._connection = await self._connection.execution_options(
                isolation_level=self._isolation_level.value
            )
        self._transaction = await self._connection.begin()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        transaction = self._transaction
        if transaction is not None and transaction.is_active:
            # Old-system semantics: an uncommitted scope is discarded, never
            # silently committed (SqlUnitOfWork.__aexit__ rolled back on
            # failure and abandoned work was rolled back on close).
            await transaction.rollback()
        if self._outcome is TransactionOutcome.ACTIVE:
            self._outcome = TransactionOutcome.ROLLED_BACK
        self._transaction = None
        return False

    async def commit(self) -> None:
        """Atomically persist all work performed inside the scope."""
        transaction = self._require_active("commit")
        await transaction.commit()
        self._outcome = TransactionOutcome.COMMITTED

    async def rollback(self) -> None:
        """Discard all work performed inside the scope."""
        transaction = self._require_active("roll back")
        await transaction.rollback()
        self._outcome = TransactionOutcome.ROLLED_BACK

    def _require_active(self, operation: str) -> AsyncTransaction:
        transaction = self._transaction
        if transaction is None or not transaction.is_active:
            raise TransactionScopeError(
                f"cannot {operation} on a transaction scope whose outcome is "
                f"{self._outcome.value!r}"
            )
        return transaction
