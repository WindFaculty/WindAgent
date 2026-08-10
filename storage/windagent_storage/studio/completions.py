"""A5 — terminal Studio completion queries (storage layer owns ORM access).

The worker's ``StudioCompletionRecovery`` must not import ORM models (the
architecture checker forbids ORM imports in application layers); this module
is the storage-side seam that turns ``task_runs`` terminal rows into plain
facts dicts the worker can reconcile.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_storage.orm.v2_orchestration_models import TaskRunORM

TERMINAL_TASK_STATES = ("completed", "failed", "cancelled")


async def list_terminal_studio_completions(
    session_factory: async_sessionmaker[AsyncSession],
) -> List[Dict[str, Any]]:
    """Terminal Studio task rows (``facts_json`` carries ``studio_envelope``).

    Returns ``[{"task_id": ..., "facts": {...}}]`` — plain data, no ORM
    objects leave the storage layer.
    """
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(TaskRunORM)
                .where(TaskRunORM.state.in_(TERMINAL_TASK_STATES))
                .where(TaskRunORM.facts_json.like("%studio_envelope%"))
            )
        ).scalars()
        rows = list(rows)
    result: List[Dict[str, Any]] = []
    for task in rows:
        try:
            facts = json.loads(task.facts_json or "{}")
        except (TypeError, ValueError):
            facts = {}
        result.append({"task_id": task.id, "facts": facts if isinstance(facts, dict) else {}})
    return result


__all__ = ["list_terminal_studio_completions", "TERMINAL_TASK_STATES"]
