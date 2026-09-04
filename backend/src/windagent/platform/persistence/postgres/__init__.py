"""PostgreSQL-specific persistence adapters (plan section 8 target)."""

from .cas import compare_and_swap_update
from .errors import (
    SQLSTATE_ADMIN_SHUTDOWN,
    SQLSTATE_CONNECTION_DOES_NOT_EXIST,
    SQLSTATE_CONNECTION_EXCEPTION,
    SQLSTATE_CONNECTION_FAILURE,
    SQLSTATE_CONNECTION_REJECTED,
    SQLSTATE_CONNECTION_UNABLE,
    SQLSTATE_CRASH_SHUTDOWN,
    SQLSTATE_DEADLOCK_DETECTED,
    SQLSTATE_LOCK_NOT_AVAILABLE,
    SQLSTATE_SERIALIZATION_FAILURE,
    SQLSTATE_TRANSACTION_UNKNOWN,
    SQLSTATE_UNIQUE_VIOLATION,
    extract_sqlstate,
    is_transient_error,
    is_unique_violation,
)
from .locks import (
    AdvisoryLockKey,
    advisory_lock_key,
    advisory_session_lock,
    advisory_session_unlock,
    advisory_xact_lock,
    try_advisory_session_lock,
    try_advisory_xact_lock,
)
from .upsert import upsert_row

__all__ = [
    "SQLSTATE_ADMIN_SHUTDOWN",
    "SQLSTATE_CONNECTION_DOES_NOT_EXIST",
    "SQLSTATE_CONNECTION_EXCEPTION",
    "SQLSTATE_CONNECTION_FAILURE",
    "SQLSTATE_CONNECTION_REJECTED",
    "SQLSTATE_CONNECTION_UNABLE",
    "SQLSTATE_CRASH_SHUTDOWN",
    "SQLSTATE_DEADLOCK_DETECTED",
    "SQLSTATE_LOCK_NOT_AVAILABLE",
    "SQLSTATE_SERIALIZATION_FAILURE",
    "SQLSTATE_TRANSACTION_UNKNOWN",
    "SQLSTATE_UNIQUE_VIOLATION",
    "AdvisoryLockKey",
    "advisory_lock_key",
    "advisory_session_lock",
    "advisory_session_unlock",
    "advisory_xact_lock",
    "compare_and_swap_update",
    "extract_sqlstate",
    "is_transient_error",
    "is_unique_violation",
    "try_advisory_session_lock",
    "try_advisory_xact_lock",
    "upsert_row",
]
