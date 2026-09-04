"""SQLSTATE helpers preserving the old system's error classification.

The old worker classified retryable versus permanent failures from raw
database errors; V2 keeps that behavior at the persistence layer so job
runtime (Phase 7) and outbox dispatch (Phase 6) reuse one classifier.
"""

from __future__ import annotations

from typing import Protocol

SQLSTATE_SERIALIZATION_FAILURE = "40001"
SQLSTATE_DEADLOCK_DETECTED = "40P01"
SQLSTATE_LOCK_NOT_AVAILABLE = "55P03"
SQLSTATE_UNIQUE_VIOLATION = "23505"
SQLSTATE_ADMIN_SHUTDOWN = "57P01"
SQLSTATE_CRASH_SHUTDOWN = "57P02"
SQLSTATE_CONNECTION_EXCEPTION = "08000"
SQLSTATE_CONNECTION_DOES_NOT_EXIST = "08003"
SQLSTATE_CONNECTION_FAILURE = "08006"
SQLSTATE_CONNECTION_UNABLE = "08001"
SQLSTATE_CONNECTION_REJECTED = "08004"
SQLSTATE_TRANSACTION_UNKNOWN = "08007"

_TRANSIENT_SQLSTATES = frozenset(
    {
        SQLSTATE_SERIALIZATION_FAILURE,
        SQLSTATE_DEADLOCK_DETECTED,
        SQLSTATE_LOCK_NOT_AVAILABLE,
        SQLSTATE_ADMIN_SHUTDOWN,
        SQLSTATE_CRASH_SHUTDOWN,
        SQLSTATE_CONNECTION_EXCEPTION,
        SQLSTATE_CONNECTION_DOES_NOT_EXIST,
        SQLSTATE_CONNECTION_FAILURE,
        SQLSTATE_CONNECTION_UNABLE,
        SQLSTATE_CONNECTION_REJECTED,
        SQLSTATE_TRANSACTION_UNKNOWN,
    }
)


class SQLStateCarrier(Protocol):
    """Anything that carries a PostgreSQL SQLSTATE, e.g. asyncpg errors."""

    sqlstate: str | None


def extract_sqlstate(error: BaseException, *, max_depth: int = 3) -> str | None:
    """Return the SQLSTATE attached to ``error`` or its wrapper chain.

    asyncpg attaches ``sqlstate``; SQLAlchemy DBAPI errors expose the driver
    exception as ``orig`` (usually also ``__cause__``).  The chain walk is
    depth-limited and cycle-safe.
    """
    current: BaseException | None = error
    for _ in range(max_depth + 1):
        if current is None:
            return None
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(current, attribute, None)
            if isinstance(value, str) and value:
                return value
        following = getattr(current, "orig", None)
        if following is current or not isinstance(following, BaseException):
            following = current.__cause__
        if following is current:
            return None
        current = following
    return None


def is_transient_error(error: BaseException) -> bool:
    """Classify whether ``error`` may succeed on a retry.

    Serialization failures, deadlocks, lock timeouts and connection-class
    failures are transient; integrity violations and application bugs are
    not.
    """
    sqlstate = extract_sqlstate(error)
    return sqlstate is not None and sqlstate in _TRANSIENT_SQLSTATES


def is_unique_violation(error: BaseException) -> bool:
    """Classify a unique-constraint violation (idempotency dedup checks)."""
    return extract_sqlstate(error) == SQLSTATE_UNIQUE_VIOLATION
