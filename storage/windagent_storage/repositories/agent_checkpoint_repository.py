"""SQL implementation for Agent Checkpoints (Phase 5)."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.durable_checkpoint import (
    assert_no_host_authority,
    ensure_json_serializable,
    sanitize_snapshot,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _sanitize(self, snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
        raw = dict(snapshot or {})
        assert_no_host_authority(raw, "checkpoint snapshot")
        cleaned = sanitize_snapshot(raw)
        ensure_json_serializable(cleaned, "checkpoint snapshot")
        return cleaned

    async def create_checkpoint(
        self,
        *,
        checkpoint_id: str,
        agent_run_id: str,
        kind: str,
        snapshot: Mapping[str, Any] | None = None,
        session_id: str | None = None,
        step_run_id: str | None = None,
        tool_name: str | None = None,
        fencing_token: str | None = None,
    ) -> dict[str, Any]:
        cleaned = self._sanitize(snapshot)
        # sequence per agent_run_id: count existing +1 within transaction
        existing = await self._session.execute(
            text("SELECT COALESCE(MAX(sequence), -1) AS max_seq FROM agent_checkpoints WHERE agent_run_id=:aid"),
            {"aid": agent_run_id},
        )
        max_seq = int(existing.mappings().first()["max_seq"])  # type: ignore
        seq = max_seq + 1

        # loop_version_at_checkpoint: read from agent_loop_states if exists
        loop_row = (
            await self._session.execute(
                text("SELECT version FROM agent_loop_states WHERE agent_run_id=:id"), {"id": agent_run_id}
            )
        ).mappings().first()
        loop_version = int(loop_row["version"]) if loop_row else 1

        now = _utc_now()
        await self._session.execute(
            text(
                """INSERT INTO agent_checkpoints
                (checkpoint_id, agent_run_id, session_id, kind, step_run_id, tool_name,
                 fencing_token, snapshot_json, sequence, loop_version_at_checkpoint, created_at)
                VALUES (:cid, :aid, :sid, :kind, :step, :tool, :fence, :snapshot_json, :seq, :loop_ver, :now)"""
            ),
            {
                "cid": checkpoint_id,
                "aid": agent_run_id,
                "sid": session_id,
                "kind": kind,
                "step": step_run_id,
                "tool": tool_name,
                "fence": fencing_token or "",
                "snapshot_json": json.dumps(cleaned),
                "seq": seq,
                "loop_ver": loop_version,
                "now": now,
            },
        )
        row = await self.get_checkpoint(checkpoint_id)
        assert row is not None
        return row

    async def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text("SELECT * FROM agent_checkpoints WHERE checkpoint_id=:id"), {"id": checkpoint_id}
            )
        ).mappings().first()
        return self._decode(dict(row)) if row else None

    async def list_checkpoints(self, agent_run_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        base = "SELECT * FROM agent_checkpoints WHERE agent_run_id=:aid"
        params: dict[str, Any] = {"aid": agent_run_id}
        if kind is not None:
            base += " AND kind=:kind"
            params["kind"] = kind
        base += " ORDER BY sequence ASC"
        rows = (await self._session.execute(text(base), params)).mappings().all()
        return [self._decode(dict(r)) for r in rows]

    async def latest_checkpoint(self, agent_run_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text("SELECT * FROM agent_checkpoints WHERE agent_run_id=:aid ORDER BY sequence DESC LIMIT 1"),
                {"aid": agent_run_id},
            )
        ).mappings().first()
        return self._decode(dict(row)) if row else None

    async def count_checkpoints(self, agent_run_id: str) -> int:
        row = (
            await self._session.execute(
                text("SELECT COUNT(*) AS cnt FROM agent_checkpoints WHERE agent_run_id=:aid"),
                {"aid": agent_run_id},
            )
        ).mappings().first()
        return int(row["cnt"]) if row else 0

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.pop("snapshot_json", "{}")
        try:
            # json loads then deep copy so mutating returned dict does not affect store
            parsed = json.loads(raw or "{}")
            row["snapshot"] = copy.deepcopy(parsed)
        except Exception:
            row["snapshot"] = {}
        return row
