"""PostgreSQL advisory locks for leader election and serialized sections.

Advisory locks back recovery leader leases and other "exactly one actor"
sections.  Transaction-scoped locks release at commit/rollback; session
locks must be released explicitly.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

type AdvisoryLockKey = str | tuple[int, int]
"""A named lock (hashed deterministically) or an explicit (classid, objid) pair."""

_INT32_MASK = 0xFFFFFFFF
_INT32_SIGN = 0x80000000
_INT32_WRAP = 0x100000000


def advisory_lock_key(name: str) -> tuple[int, int]:
    """Hash ``name`` into a stable (classid, objid) pair of signed int32s.

    The mapping is deterministic across processes and restarts, so every
    actor computing the key for the same section name contends on the same
    lock.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("advisory lock name must be non-empty text")
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return (
        _to_signed_int32(int.from_bytes(digest[:4], "big")),
        _to_signed_int32(int.from_bytes(digest[4:8], "big")),
    )


async def try_advisory_xact_lock(
    connection: AsyncConnection, key: AdvisoryLockKey
) -> bool:
    """Try to take a transaction-scoped advisory lock without blocking.

    The lock is held until the current transaction commits or rolls back and
    is released automatically.
    """
    class_id, object_id = _normalize_key(key)
    result = await connection.execute(
        text("SELECT pg_try_advisory_xact_lock(:class_id, :object_id)"),
        {"class_id": class_id, "object_id": object_id},
    )
    return bool(result.scalar_one())


async def advisory_xact_lock(connection: AsyncConnection, key: AdvisoryLockKey) -> None:
    """Take a transaction-scoped advisory lock, blocking until available."""
    class_id, object_id = _normalize_key(key)
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(:class_id, :object_id)"),
        {"class_id": class_id, "object_id": object_id},
    )


async def try_advisory_session_lock(
    connection: AsyncConnection, key: AdvisoryLockKey
) -> bool:
    """Try to take a session-scoped advisory lock without blocking.

    The lock is bound to the connection and must be released with
    :func:`advisory_session_unlock` or dies with the connection.
    """
    class_id, object_id = _normalize_key(key)
    result = await connection.execute(
        text("SELECT pg_try_advisory_lock(:class_id, :object_id)"),
        {"class_id": class_id, "object_id": object_id},
    )
    return bool(result.scalar_one())


async def advisory_session_lock(connection: AsyncConnection, key: AdvisoryLockKey) -> None:
    """Take a session-scoped advisory lock, blocking until available."""
    class_id, object_id = _normalize_key(key)
    await connection.execute(
        text("SELECT pg_advisory_lock(:class_id, :object_id)"),
        {"class_id": class_id, "object_id": object_id},
    )


async def advisory_session_unlock(
    connection: AsyncConnection, key: AdvisoryLockKey
) -> bool:
    """Release a session-scoped advisory lock; ``False`` if not held."""
    class_id, object_id = _normalize_key(key)
    result = await connection.execute(
        text("SELECT pg_advisory_unlock(:class_id, :object_id)"),
        {"class_id": class_id, "object_id": object_id},
    )
    return bool(result.scalar_one())


def _normalize_key(key: AdvisoryLockKey) -> tuple[int, int]:
    if isinstance(key, str):
        return advisory_lock_key(key)
    class_id, object_id = key
    return _to_signed_int32(class_id), _to_signed_int32(object_id)


def _to_signed_int32(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("advisory lock key components must be integers")
    normalized = value & _INT32_MASK
    return normalized - _INT32_WRAP if normalized >= _INT32_SIGN else normalized
