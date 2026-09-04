"""Persistence transaction contract with no ORM or database dependency."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Literal, Self


class UnitOfWork(ABC):
    """An explicit asynchronous transaction boundary.

    Repositories, SQLAlchemy sessions, database engines, and the transactional
    outbox are deliberately not introduced until later foundation phases.
    """

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Open the transaction scope."""

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Close the scope without suppressing application exceptions."""

    @abstractmethod
    async def commit(self) -> None:
        """Atomically persist the work accumulated in this scope."""

    @abstractmethod
    async def rollback(self) -> None:
        """Discard the work accumulated in this scope."""
