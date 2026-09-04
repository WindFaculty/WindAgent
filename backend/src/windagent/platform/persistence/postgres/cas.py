"""Optimistic compare-and-swap (CAS) updates on versioned rows.

Preserved semantics from the old durable queue and task finalizer: an
update only applies when the row's version still equals the expected
value, the version is incremented in the same statement, and a zero
rowcount means the caller lost the race (stale write) rather than an
error.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import Table, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


async def compare_and_swap_update(
    executor: AsyncConnection | AsyncSession,
    table: Table,
    *,
    key_column: str,
    key_value: object,
    expected_version: int,
    version_column: str = "version",
    values: Mapping[str, object] | None = None,
    version_increment: int = 1,
) -> bool:
    """Conditionally update one row identified by ``key_column``.

    The row is updated only when ``version_column`` still equals
    ``expected_version``; the version is bumped by ``version_increment``
    within the same atomic statement.  Returns ``True`` when this caller
    won the race and ``False`` when the row was concurrently modified.
    """
    if expected_version < 0:
        raise ValueError("expected_version must be non-negative")
    if version_increment < 1:
        raise ValueError("version_increment must be at least 1")

    columns = table.c
    payload: dict[str, object] = dict(values or {})
    payload[version_column] = columns[version_column] + version_increment

    statement = (
        update(table)
        .where(
            columns[key_column] == key_value,
            columns[version_column] == expected_version,
        )
        .values(**payload)
    )
    result = await executor.execute(statement)
    return cast("CursorResult[Any]", result).rowcount == 1
