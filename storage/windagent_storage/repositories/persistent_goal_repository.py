"""SQL implementation for Persistent Goals (Phase 5)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersistentGoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_goal(
        self,
        *,
        goal_id: str,
        objective: str,
        status: str = "ACTIVE",
        progress_summary: str = "",
        completion_criteria: Mapping[str, Any] | None = None,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
        agent_run_id: str | None = None,
        harness_version: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        await self._session.execute(
            text(
                """INSERT INTO persistent_goals
                (goal_id, objective, status, progress_summary, completion_criteria_json, blocked_reason,
                 conversation_id, parent_task_id, agent_run_id, harness_version, version,
                 started_at, last_progress_at, created_at, updated_at)
                VALUES (:goal_id, :objective, :status, :progress_summary, :criteria_json, NULL,
                        :conv_id, :parent_id, :agent_run_id, :harness_version, 1,
                        :now, NULL, :now, :now)"""
            ),
            {
                "goal_id": goal_id,
                "objective": objective,
                "status": status,
                "progress_summary": progress_summary,
                "criteria_json": json.dumps(dict(completion_criteria or {})),
                "conv_id": conversation_id,
                "parent_id": parent_task_id,
                "agent_run_id": agent_run_id,
                "harness_version": harness_version,
                "now": now,
            },
        )
        row = await self.get_goal(goal_id)
        assert row is not None
        return row

    async def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text("SELECT * FROM persistent_goals WHERE goal_id=:id"), {"id": goal_id}
            )
        ).mappings().first()
        return self._decode(dict(row)) if row else None

    async def list_goals(
        self,
        *,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        base = "SELECT * FROM persistent_goals WHERE 1=1"
        params: dict[str, Any] = {}
        if conversation_id is not None:
            base += " AND conversation_id=:conv"
            params["conv"] = conversation_id
        if parent_task_id is not None:
            base += " AND parent_task_id=:parent"
            params["parent"] = parent_task_id
        if status is not None:
            base += " AND status=:status"
            params["status"] = status
        base += " ORDER BY created_at ASC"
        rows = (await self._session.execute(text(base), params)).mappings().all()
        return [self._decode(dict(r)) for r in rows]

    async def update_progress(
        self, *, goal_id: str, expected_version: int, progress_summary: str
    ) -> dict[str, Any] | None:
        now = _utc_now()
        result = await self._session.execute(
            text(
                """UPDATE persistent_goals
                   SET progress_summary=:summary, last_progress_at=:now, version=version+1, updated_at=:now
                   WHERE goal_id=:goal_id AND version=:expected_version"""
            ),
            {"goal_id": goal_id, "summary": progress_summary, "now": now, "expected_version": expected_version},
        )
        if result.rowcount != 1:
            return None
        return await self.get_goal(goal_id)

    async def transition_status(
        self,
        *,
        goal_id: str,
        expected_version: int,
        target_status: str,
        reason: str | None = None,
        blocked_reason: str | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_now()
        # For BLOCKED we set blocked_reason, otherwise clear on non-BLOCKED unless explicitly provided
        result = await self._session.execute(
            text(
                """UPDATE persistent_goals
                   SET status=:target_status,
                       blocked_reason=CASE WHEN :target_status='BLOCKED' THEN COALESCE(:blocked_reason, blocked_reason) ELSE NULL END,
                       last_progress_at=:now,
                       version=version+1,
                       updated_at=:now
                   WHERE goal_id=:goal_id AND version=:expected_version"""
            ),
            {
                "goal_id": goal_id,
                "target_status": target_status,
                "blocked_reason": blocked_reason or reason,
                "now": now,
                "expected_version": expected_version,
            },
        )
        if result.rowcount != 1:
            return None
        return await self.get_goal(goal_id)

    async def update_completion_criteria(
        self, *, goal_id: str, expected_version: int, criteria: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        now = _utc_now()
        result = await self._session.execute(
            text(
                """UPDATE persistent_goals
                   SET completion_criteria_json=:criteria_json, version=version+1, updated_at=:now
                   WHERE goal_id=:goal_id AND version=:expected_version"""
            ),
            {
                "goal_id": goal_id,
                "criteria_json": json.dumps(dict(criteria or {})),
                "now": now,
                "expected_version": expected_version,
            },
        )
        if result.rowcount != 1:
            return None
        return await self.get_goal(goal_id)

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.pop("completion_criteria_json", "{}")
        try:
            row["completion_criteria"] = json.loads(raw or "{}")
        except Exception:
            row["completion_criteria"] = {}
        return row
