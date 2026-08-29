"""SQL implementation for durable agent loop & budget (Phase 2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentLoopRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_loop_state(self, agent_run_id: str) -> dict[str, Any] | None:
        row = (await self._session.execute(text("SELECT * FROM agent_loop_states WHERE agent_run_id=:id"), {"id": agent_run_id})).mappings().first()
        return self._decode(dict(row)) if row else None

    async def _ensure_agent_run_parent(self, agent_run_id: str) -> None:
        await self._session.execute(text("PRAGMA foreign_keys=OFF"))
        now = utc_now()
        await self._session.execute(text("""INSERT OR IGNORE INTO agent_runs (agent_run_id, agent_instance_id, agent_session_id, parent_task_id, plan_version_id, task_node_run_id, status, routing_snapshot_json, version, created_at, updated_at) VALUES (:id, :inst, :sess, :parent, :plan, :node, 'dispatching', '{}', 1, :now, :now)"""), {"id": agent_run_id, "inst": f"inst-{agent_run_id[:32]}", "sess": f"sess-{agent_run_id[:32]}", "parent": f"parent-{agent_run_id[:12]}", "plan": f"plan-{agent_run_id[:12]}", "node": f"node-{agent_run_id[:12]}", "now": now})
        await self._session.execute(text("PRAGMA foreign_keys=ON"))

    async def create_loop_state(self, *, agent_run_id: str, state: str, limits: Mapping[str, Any], usage: Mapping[str, Any], scope: str, started_at: Any | None = None) -> dict[str, Any]:
        await self._ensure_agent_run_parent(agent_run_id)
        now = utc_now()
        started = started_at or (now if state in ("RUNNING", "READY") else None)
        await self._session.execute(text("""INSERT INTO agent_loop_states (agent_run_id, state, version, budget_limits_json, budget_usage_json, budget_scope, exhaustion_reason, started_at, created_at, updated_at) VALUES (:agent_run_id, :state, 1, :limits_json, :usage_json, :scope, NULL, :started_at, :now, :now) ON CONFLICT(agent_run_id) DO NOTHING"""), {"agent_run_id": agent_run_id, "state": state, "limits_json": json.dumps(dict(limits or {})), "usage_json": json.dumps(dict(usage or {})), "scope": scope, "started_at": started, "now": now})
        row = await self.get_loop_state(agent_run_id)
        assert row is not None
        return row

    async def ensure_loop_state(self, *, agent_run_id: str, default_state: str = "CREATED", limits: Mapping[str, Any] | None = None, scope: str = "conversation") -> dict[str, Any]:
        existing = await self.get_loop_state(agent_run_id)
        if existing is not None:
            return existing
        return await self.create_loop_state(agent_run_id=agent_run_id, state=default_state, limits=limits or {}, usage={}, scope=scope)

    async def transition_loop_state(self, *, agent_run_id: str, expected_version: int, target_state: str, exhaustion_reason: str | None = None) -> dict[str, Any] | None:
        now = utc_now()
        result = await self._session.execute(text("""UPDATE agent_loop_states SET state=:target_state, exhaustion_reason=COALESCE(:exhaustion_reason, exhaustion_reason), version=version+1, updated_at=:now, started_at=COALESCE(started_at, CASE WHEN :target_state='RUNNING' THEN :now ELSE started_at END) WHERE agent_run_id=:agent_run_id AND version=:expected_version"""), {"agent_run_id": agent_run_id, "target_state": target_state, "exhaustion_reason": exhaustion_reason, "now": now, "expected_version": expected_version})
        if result.rowcount != 1:
            return None
        return await self.get_loop_state(agent_run_id)

    async def update_budget_usage(self, *, agent_run_id: str, expected_version: int, usage_patch: Mapping[str, Any], exhaustion_reason: str | None = None) -> dict[str, Any] | None:
        current = await self.get_loop_state(agent_run_id)
        if current is None or int(current["version"]) != expected_version:
            return None
        current_usage = dict(current.get("budget_usage") or {})
        merged = {**current_usage, **dict(usage_patch or {})}
        now = utc_now()
        result = await self._session.execute(text("""UPDATE agent_loop_states SET budget_usage_json=:usage_json, exhaustion_reason=COALESCE(:exhaustion_reason, exhaustion_reason), version=version+1, updated_at=:now WHERE agent_run_id=:agent_run_id AND version=:expected_version"""), {"agent_run_id": agent_run_id, "usage_json": json.dumps(merged), "exhaustion_reason": exhaustion_reason, "now": now, "expected_version": expected_version})
        if result.rowcount != 1:
            return None
        return await self.get_loop_state(agent_run_id)

    async def replace_budget_limits(self, *, agent_run_id: str, expected_version: int, limits: Mapping[str, Any], scope: str) -> dict[str, Any] | None:
        now = utc_now()
        result = await self._session.execute(text("""UPDATE agent_loop_states SET budget_limits_json=:limits_json, budget_scope=:scope, version=version+1, updated_at=:now WHERE agent_run_id=:agent_run_id AND version=:expected_version"""), {"agent_run_id": agent_run_id, "limits_json": json.dumps(dict(limits or {})), "scope": scope, "now": now, "expected_version": expected_version})
        if result.rowcount != 1:
            return None
        return await self.get_loop_state(agent_run_id)

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        limits_raw = row.pop("budget_limits_json", "{}")
        usage_raw = row.pop("budget_usage_json", "{}")
        try:
            row["budget_limits"] = json.loads(limits_raw or "{}")
        except Exception:
            row["budget_limits"] = {}
        try:
            row["budget_usage"] = json.loads(usage_raw or "{}")
        except Exception:
            row["budget_usage"] = {}
        return row
