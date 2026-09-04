"""PostgreSQL upserts (``INSERT ... ON CONFLICT DO UPDATE``).

Used by idempotent writers that must converge instead of racing unique
constraints.  Column names are resolved eagerly so misconfiguration fails
before a statement reaches the database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


async def upsert_row(
    executor: AsyncConnection | AsyncSession,
    table: Table,
    *,
    conflict_columns: Sequence[str],
    values: Mapping[str, object],
    update_columns: Sequence[str] | None = None,
) -> bool:
    """Insert ``values`` or update the conflicting row in one statement.

    ``conflict_columns`` name the unique constraint target.  By default every
    non-conflict column is updated; pass ``update_columns`` to narrow it.
    Returns ``True`` when a row was written (insert or update).
    """
    if not conflict_columns:
        raise ValueError("conflict_columns must not be empty")
    if not values:
        raise ValueError("values must not be empty")

    resolved_conflict = tuple(table.c[name] for name in conflict_columns)
    payload: dict[str, object] = dict(values)
    targets = (
        tuple(update_columns)
        if update_columns is not None
        else tuple(name for name in payload if name not in conflict_columns)
    )

    statement = postgres_insert(table).values(payload).on_conflict_do_update(
        index_elements=resolved_conflict,
        set_={name: payload[name] for name in targets},
    )
    result = await executor.execute(statement)
    return cast("CursorResult[Any]", result).rowcount > 0
