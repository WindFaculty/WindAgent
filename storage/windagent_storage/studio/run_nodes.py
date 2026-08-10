"""Durable Studio run-node repository (Plan A — A4, studio.contract/v0.1).

Per-node state of a Studio story run lives in ``studio_run_nodes``. The
orchestrator persists DAG/node state BEFORE any durable submission and marks a
node DISPATCHED only with a committed queue task identity. Every state write is
optimistic (``version`` CAS) so stale completions and concurrent resubmissions
fail closed with ``StudioStaleNodeError``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.contracts.studio.errors import (
    StudioNotFoundError,
    StudioStaleNodeError,
)
from windagent_core.contracts.studio.ids import StudioRunId
from windagent_core.contracts.studio.models import StudioNodeStatus
from windagent_storage.orm.studio_models import StudioRunNodeORM


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _node_from_orm(row: StudioRunNodeORM) -> Dict[str, Any]:
    return {
        "run_id": row.run_id,
        "dag_node_id": row.dag_node_id,
        "task_type": row.task_type,
        "status": row.status,
        "task_id": row.task_id,
        "attempt": row.attempt,
        "depends_on": _loads(row.depends_on_json, []),
        "checkpoint": row.checkpoint,
        "gate": bool(row.gate),
        "input_hashes": _loads(row.input_hashes_json, []),
        "output_hashes": _loads(row.output_hashes_json, []),
        "output_artifact_refs": _loads(row.output_artifact_refs_json, []),
        "error": row.error,
        "version": row.version,
        "updated_at": row.updated_at,
    }


class SqlStudioRunNodeRepository:
    """Optimistic, session-scoped repository for ``studio_run_nodes``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_nodes(self, run_id: StudioRunId, nodes: Dict[str, Dict[str, Any]]) -> None:
        """Insert new nodes / refresh existing ones in the current transaction.

        Used at run start and on resume; state transitions go through
        ``update_node`` with a version CAS instead.
        """
        now = _naive(datetime.now(timezone.utc))
        run_key = str(run_id)
        existing_stmt = select(StudioRunNodeORM).where(StudioRunNodeORM.run_id == run_key)
        existing = {
            row.dag_node_id: row
            for row in (await self.session.execute(existing_stmt)).scalars().all()
        }
        for node_id, node in nodes.items():
            row = existing.get(node_id)
            if row is None:
                self.session.add(
                    StudioRunNodeORM(
                        run_id=run_key,
                        dag_node_id=node_id,
                        task_type=node["task_type"],
                        status=node.get("status", StudioNodeStatus.PENDING.value),
                        task_id=node.get("task_id"),
                        attempt=node.get("attempt", 1),
                        depends_on_json=_dumps(node.get("depends_on", [])),
                        checkpoint=node.get("checkpoint"),
                        gate=bool(node.get("gate", False)),
                        input_hashes_json=_dumps(node.get("input_hashes", [])),
                        output_hashes_json=_dumps(node.get("output_hashes", [])),
                        output_artifact_refs_json=_dumps(node.get("output_artifact_refs", [])),
                        error=node.get("error"),
                        version=node.get("version", 0),
                        updated_at=now,
                    )
                )
            else:
                row.task_type = node.get("task_type", row.task_type)
                row.depends_on_json = _dumps(node.get("depends_on", _loads(row.depends_on_json, [])))
                row.checkpoint = node.get("checkpoint", row.checkpoint)
                row.gate = bool(node.get("gate", row.gate))
                row.updated_at = now

    async def get(self, run_id: StudioRunId, dag_node_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(StudioRunNodeORM).where(
            StudioRunNodeORM.run_id == str(run_id),
            StudioRunNodeORM.dag_node_id == dag_node_id,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _node_from_orm(row) if row is not None else None

    async def list(self, run_id: StudioRunId) -> List[Dict[str, Any]]:
        stmt = (
            select(StudioRunNodeORM)
            .where(StudioRunNodeORM.run_id == str(run_id))
            .order_by(StudioRunNodeORM.dag_node_id)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_node_from_orm(r) for r in rows]

    async def get_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(StudioRunNodeORM).where(StudioRunNodeORM.task_id == task_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _node_from_orm(row) if row is not None else None

    async def update_node(
        self,
        run_id: StudioRunId,
        dag_node_id: str,
        *,
        expected_version: int,
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Optimistic state write; raises on version mismatch or missing node."""
        now = _naive(datetime.now(timezone.utc))
        payload: Dict[str, Any] = {
            "status": values["status"],
            "updated_at": now,
            "version": expected_version + 1,
        }
        for key in (
            "task_id",
            "attempt",
            "input_hashes",
            "output_hashes",
            "output_artifact_refs",
            "error",
        ):
            if key in values:
                if key in ("input_hashes", "output_hashes", "output_artifact_refs"):
                    payload[f"{key}_json"] = _dumps(values[key])
                else:
                    payload[key] = values[key]
        stmt = (
            update(StudioRunNodeORM)
            .where(
                StudioRunNodeORM.run_id == str(run_id),
                StudioRunNodeORM.dag_node_id == dag_node_id,
                StudioRunNodeORM.version == expected_version,
            )
            .values(**payload)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            current = await self.get(run_id, dag_node_id)
            if current is None:
                raise StudioNotFoundError(
                    f"Run node {dag_node_id!r} of run {run_id!s} does not exist.",
                    details={"run_id": str(run_id), "dag_node_id": dag_node_id},
                )
            raise StudioStaleNodeError(
                f"Stale write to run node {dag_node_id!r}: expected version "
                f"{expected_version}, current {current['version']}.",
                details={
                    "run_id": str(run_id),
                    "dag_node_id": dag_node_id,
                    "expected_version": expected_version,
                    "current_version": current["version"],
                },
            )
        return {**values, "version": expected_version + 1, "updated_at": now}


__all__ = ["SqlStudioRunNodeRepository"]
