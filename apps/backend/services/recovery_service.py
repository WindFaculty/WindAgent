"""Phase 7 — durable event replay + restart recovery (ban_ke_hoach §11-12).

Two jobs:

  replay_after(session_id, after_seq)   -> events the client missed
  seed_seq(session_id)                  -> last persisted seq (EventBus seed)
  recover()                             -> reconcile in-flight agent runs
                                           against the Hermes server on boot

Recovery is conservative: a run whose Hermes run no longer exists is marked
`interrupted` and its task set `retryable` — the orchestrator decides retry,
we never silently mark work completed (§12).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select

from db.database import Database
from db.models import (
    AgentInstanceORM,
    AgentRunORM,
    ExecutionEventORM,
    TaskNodeORM,
)
from schemas.event import EventEnvelope

log = logging.getLogger(__name__)


class RecoveryManager:
    def __init__(self, db: Database, *, hermes_api_client=None) -> None:
        self.db = db
        self.client = hermes_api_client

    # ---------- replay ----------

    async def seed_seq(self, session_id: str) -> int:
        """Last persisted event_seq for a session, 0 if none."""
        async with self.db.session() as s:
            row = await s.execute(
                select(func.max(ExecutionEventORM.event_seq)).where(
                    ExecutionEventORM.session_id == session_id
                )
            )
            return row.scalar() or 0

    async def replay_after(
        self, session_id: str, after_seq: int, *, limit: int = 1000
    ) -> List[EventEnvelope]:
        """Return persisted events with seq > after_seq, in order."""
        async with self.db.session() as s:
            rows = (await s.execute(
                select(ExecutionEventORM)
                .where(
                    ExecutionEventORM.session_id == session_id,
                    ExecutionEventORM.event_seq > after_seq,
                )
                .order_by(ExecutionEventORM.event_seq)
                .limit(limit)
            )).scalars().all()
        out: List[EventEnvelope] = []
        for r in rows:
            out.append(EventEnvelope(
                event=r.event_type,  # type: ignore[arg-type]
                timestamp=r.created_at,
                data=json.loads(r.data_json or "{}"),
                seq=r.event_seq,
            ))
        return out

    # ---------- restart recovery ----------

    async def recover(self) -> dict:
        """Reconcile running agent runs after a backend restart (§12).

        For each AgentRun still marked running, ask Hermes if the run is
        alive. Dead run -> AgentRun=interrupted, its task=retryable.
        Returns a small summary for logging/tests.
        """
        reattached, interrupted = 0, 0
        async with self.db.session() as s:
            runs = (await s.execute(
                select(AgentRunORM).where(AgentRunORM.status == "running")
            )).scalars().all()

            for run in runs:
                alive = await self._run_alive(run.hermes_run_id)
                if alive:
                    reattached += 1
                    continue
                run.status = "interrupted"
                run.finished_at = datetime.now(timezone.utc)
                interrupted += 1
                # Mark owning instance + task retryable.
                if run.agent_instance_id:
                    inst = await s.get(AgentInstanceORM, run.agent_instance_id)
                    if inst:
                        inst.status = "interrupted"
                if run.task_id:
                    task = await s.get(TaskNodeORM, run.task_id)
                    if task and task.status in ("running", "assigned"):
                        task.status = "retryable"

        log.info("recovery: reattached=%d interrupted=%d", reattached, interrupted)
        return {"reattached": reattached, "interrupted": interrupted}

    async def _run_alive(self, hermes_run_id: Optional[str]) -> bool:
        if not hermes_run_id or self.client is None:
            return False
        try:
            info = await self.client.get_run(hermes_run_id)
        except Exception:  # noqa: BLE001
            return False
        return info.get("status") in ("running", "pending", "queued")
