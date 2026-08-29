"""SQL implementation for durable delegation (Phase 4)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
def utc_now() -> datetime:
    return datetime.now(timezone.utc)
class DelegationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    async def create_delegation(self, *, child_agent_run_id: str, parent_agent_run_id: str, root_agent_run_id: str, delegation_depth: int, delegation_reason: str, failure_policy: str, allocated_budget: Mapping[str, Any] | None = None, bounded_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        await self._session.execute(text("""INSERT INTO agent_delegations (child_agent_run_id, parent_agent_run_id, root_agent_run_id, delegation_depth, delegation_reason, failure_policy, allocated_budget_json, child_result_summary_json, child_artifact_refs_json, bounded_context_json, version, created_at, updated_at) VALUES (:child_agent_run_id, :parent_agent_run_id, :root_agent_run_id, :delegation_depth, :delegation_reason, :failure_policy, :allocated_budget_json, NULL, :artifact_refs_json, :bounded_context_json, 1, :now, :now)"""), {"child_agent_run_id": child_agent_run_id, "parent_agent_run_id": parent_agent_run_id, "root_agent_run_id": root_agent_run_id, "delegation_depth": int(delegation_depth), "delegation_reason": delegation_reason, "failure_policy": failure_policy, "allocated_budget_json": json.dumps(dict(allocated_budget or {})), "artifact_refs_json": json.dumps([]), "bounded_context_json": json.dumps(dict(bounded_context or {})) if bounded_context else None, "now": now})
        row = await self.get_delegation(child_agent_run_id)
        assert row is not None
        return row
    async def get_delegation(self, child_agent_run_id: str) -> dict[str, Any] | None:
        return await self.get_delegation_by_child(child_agent_run_id)
    async def get_delegation_by_child(self, child_agent_run_id: str) -> dict[str, Any] | None:
        row = (await self._session.execute(text("SELECT * FROM agent_delegations WHERE child_agent_run_id=:id"), {"id": child_agent_run_id})).mappings().first()
        if row is None:
            return None
        return self._decode(dict(row))
    async def list_children(self, parent_agent_run_id: str) -> list[dict[str, Any]]:
        rows = await self._session.execute(text("SELECT * FROM agent_delegations WHERE parent_agent_run_id=:pid ORDER BY created_at ASC, delegation_depth ASC"), {"pid": parent_agent_run_id})
        return [self._decode(dict(r)) for r in rows.mappings().all()]
    async def list_tree(self, root_agent_run_id: str) -> list[dict[str, Any]]:
        rows = await self._session.execute(text("SELECT * FROM agent_delegations WHERE root_agent_run_id=:rid ORDER BY delegation_depth ASC, created_at ASC"), {"rid": root_agent_run_id})
        return [self._decode(dict(r)) for r in rows.mappings().all()]
    async def publish_child_result(self, *, child_agent_run_id: str, expected_version: int, summary: Mapping[str, Any], artifact_refs: list[str] | tuple[str, ...]) -> dict[str, Any] | None:
        now = utc_now()
        result = await self._session.execute(text("""UPDATE agent_delegations SET child_result_summary_json=:summary_json, child_artifact_refs_json=:refs_json, version=version+1, updated_at=:now WHERE child_agent_run_id=:child_agent_run_id AND version=:expected_version"""), {"child_agent_run_id": child_agent_run_id, "expected_version": expected_version, "summary_json": json.dumps(dict(summary or {})), "refs_json": json.dumps(list(artifact_refs or [])), "now": now})
        if result.rowcount != 1:
            return None
        return await self.get_delegation(child_agent_run_id)
    async def set_failure_policy(self, *, child_agent_run_id: str, expected_version: int, failure_policy: str) -> dict[str, Any] | None:
        now = utc_now()
        result = await self._session.execute(text("""UPDATE agent_delegations SET failure_policy=:policy, version=version+1, updated_at=:now WHERE child_agent_run_id=:child_agent_run_id AND version=:expected_version"""), {"child_agent_run_id": child_agent_run_id, "expected_version": expected_version, "policy": failure_policy, "now": now})
        if result.rowcount != 1:
            return None
        return await self.get_delegation(child_agent_run_id)
    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        for k in ("allocated_budget_json", "child_result_summary_json", "child_artifact_refs_json", "bounded_context_json"):
            raw = row.pop(k, None)
            if k == "allocated_budget_json":
                key = "allocated_budget"
            elif k == "child_result_summary_json":
                key = "child_result_summary"
            elif k == "child_artifact_refs_json":
                key = "child_artifact_refs"
            else:
                key = "bounded_context"
            try:
                if raw in (None, ""):
                    if "summary" in k or "bounded" in k:
                        row[key] = None
                    elif "budget" in k:
                        row[key] = {}
                    else:
                        row[key] = []
                else:
                    row[key] = json.loads(raw) if raw not in (None, "") else ({} if "summary" in k or "budget" in k else [] if "refs" in k else None)
            except Exception:
                row[key] = {} if key in ("allocated_budget", "child_result_summary", "bounded_context") else []
        return row
