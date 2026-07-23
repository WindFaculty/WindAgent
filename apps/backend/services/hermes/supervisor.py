"""Phase 4 — Hermes multi-session supervisor (ban_ke_hoach §7).

One long-lived orchestrator session per conversation. Sub-agents are
independent Hermes sessions/runs, each persisted as AgentInstance +
AgentRun. Events stream onto the conversation bus so the WebSocket
multiplexes every agent through one conversation channel.

Gate: one orchestrator spawns >= 3 independent Hermes sub-agents.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, update

from db.database import Database
from db.models import (
    AgentInstanceORM,
    AgentORM,
    AgentRunORM,
    WorktreeORM,
)
from schemas.event import EventEnvelope
from services.hermes.session_bridge import HermesSessionBridge

log = logging.getLogger(__name__)


class HermesSupervisor:
    """Owns orchestrator + sub-agent sessions for a conversation."""

    def __init__(
        self,
        db: Database,
        bridge: HermesSessionBridge,
        *,
        event_bus=None,
        worktree_service=None,
    ) -> None:
        self.db = db
        self.bridge = bridge
        self._bus = event_bus
        self._worktree = worktree_service
        # conversation_id -> orchestrator session mapping
        self._orchestrators: Dict[str, Dict[str, str]] = {}
        # run_id -> conversation_id (for stop routing)
        self._run_convo: Dict[str, str] = {}

    async def ensure_orchestrator(self, conversation_id: str, agent_id: str) -> str:
        """Create (or reuse) the long-lived orchestrator Hermes session."""
        if conversation_id in self._orchestrators:
            return self._orchestrators[conversation_id]["hermes_session_id"]

        hermes_session_id = await self.bridge.create_session(
            windagent_session_id=f"orch:{conversation_id}",
            agent_id=agent_id,
        )
        async with self.db.session() as s:
            async with s.begin():
                inst = AgentInstanceORM(
                    id=f"inst_{uuid.uuid4().hex}",
                    conversation_id=conversation_id,
                    agent_type="orchestrator",
                    status="idle",
                    permission_profile="Standard",
                )
                s.add(inst)
        self._orchestrators[conversation_id] = {
            "hermes_session_id": hermes_session_id,
            "instance_id": inst.id,
        }
        return hermes_session_id

    async def spawn_subagent(
        self,
        *,
        conversation_id: str,
        parent_task_id: Optional[str],
        task_id: Optional[str],
        agent_id: str,
        prompt: str,
        agent_type: str,
        model: Optional[str] = None,
        workspace_root: Optional[str] = None,
    ) -> Dict[str, str]:
        """Spawn an independent sub-agent run. Persists instance + run.

        Phase 6: coding agents get an isolated Git worktree; their
        workspace_root becomes the worktree path so they never write to
        the main workspace (ban_ke_hoach §9, ADR 0004).
        """
        async with self.db.session() as s:
            stmt = select(AgentORM).where(AgentORM.id == agent_id)
            agent = (await s.execute(stmt)).scalar_one_or_none()
            if not agent:
                raise ValueError(f"Agent '{agent_id}' not found")

            # Phase 6: isolate coding agents into their own worktree.
            worktree_path = workspace_root or agent.workspace_root
            worktree_id: Optional[str] = None
            if self._worktree is not None:
                wt = await self._worktree.create(
                    conversation_id=conversation_id,
                    agent_instance_id=f"inst_pending:{agent_id}",
                    agent_type=agent_type,
                    task_id=task_id,
                )
                if wt is not None:
                    worktree_path = wt.path
                    worktree_id = wt.id
                    self._emit_worktree("worktree_created", wt)

            hermes_session_id = await self.bridge.create_session(
                windagent_session_id=f"sub:{conversation_id}:{agent_id}",
                agent_id=agent_id,
                workspace_root=worktree_path,
            )
            instance = AgentInstanceORM(
                id=f"inst_{uuid.uuid4().hex}",
                conversation_id=conversation_id,
                parent_task_id=parent_task_id,
                task_id=task_id,
                agent_type=agent_type,
                status="running",
                permission_profile="Standard",
                workspace_id=worktree_path,
            )
            s.add(instance)
            await s.flush()
            instance_id = instance.id

            # Fix the placeholder worktree <-> instance mapping.
            if worktree_id is not None:
                stmt_fix = (
                    update(WorktreeORM)
                    .where(WorktreeORM.id == worktree_id)
                    .values(agent_instance_id=instance_id)
                )
                await s.execute(stmt_fix)

        run_info = await self.bridge.submit_run(
            hermes_session_id=hermes_session_id,
            agent_id=agent_id,
            content=prompt,
            conversation_id=conversation_id,
            workspace_root=worktree_path,
            model=model,
        )
        run_id = run_info["run_id"]

        async with self.db.session() as s:
            s.add(AgentRunORM(
                id=f"run_{uuid.uuid4().hex}",
                agent_instance_id=instance_id,
                hermes_session_id=hermes_session_id,
                hermes_run_id=run_id,
                task_id=task_id,
                status="running",
                started_at=datetime.now(timezone.utc),
            ))
        self._run_convo[run_id] = conversation_id

        return {
            "instance_id": instance_id,
            "hermes_session_id": hermes_session_id,
            "run_id": run_id,
            "worktree_path": worktree_path,
        }

    async def stop_subagent(self, run_id: str) -> bool:
        """Stop a sub-agent run and mark its instance/run cancelled.

        Phase 6: remove the agent's worktree (quarantined for audit).
        """
        convo = self._run_convo.get(run_id)
        ok = await self.bridge.stop_run_by_run_id(run_id)
        instance_id: Optional[str] = None
        async with self.db.session() as s:
            stmt = select(AgentRunORM).where(AgentRunORM.hermes_run_id == run_id)
            run = (await s.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "cancelled"
                run.finished_at = datetime.now(timezone.utc)
                instance_id = run.agent_instance_id
                if run.agent_instance_id:
                    inst = await s.get(AgentInstanceORM, run.agent_instance_id)
                    if inst:
                        inst.status = "cancelled"
        self._run_convo.pop(run_id, None)

        if instance_id and self._worktree is not None:
            await self._worktree.remove(instance_id, quarantine=True)
        return ok

    async def integrate_agent(
        self,
        *,
        instance_id: str,
        target_branch: str = "main",
        strategy: str = "merge",
    ) -> Dict[str, object]:
        """Phase 6 integration-agent flow: merge a coding agent's branch.

        Runs on the main workspace via WorktreeService.integrate; emits
        worktree_merged / worktree_conflict accordingly.
        """
        if self._worktree is None:
            raise RuntimeError("worktree service not configured")
        result = await self._worktree.integrate(
            agent_instance_id=instance_id,
            target_branch=target_branch,
            strategy=strategy,
        )
        event = "worktree_merged" if result["ok"] else "worktree_conflict"
        if self._bus is not None:
            env = EventEnvelope(
                event=event,
                data={
                    "agent_instance_id": instance_id,
                    "method": result.get("method"),
                    "detail": result.get("detail"),
                },
            )
            await self._bus.publish(instance_id, env)
        return result

    def _emit_worktree(self, event: str, wt) -> None:
        if self._bus is None:
            return
        env = EventEnvelope(
            event=event,
            data={
                "agent_instance_id": wt.agent_instance_id,
                "conversation_id": wt.conversation_id,
                "branch": wt.branch_name,
                "path": wt.path,
                "status": wt.status,
            },
        )
        # publish on conversation_id scope when available
        asyncio.create_task(self._bus.publish(wt.conversation_id, env))

    async def list_instances(self, conversation_id: str) -> List[AgentInstanceORM]:
        async with self.db.session() as s:
            stmt = select(AgentInstanceORM).where(
                AgentInstanceORM.conversation_id == conversation_id
            )
            return list((await s.execute(stmt)).scalars().all())

    async def reattach(self, conversation_id: str) -> None:
        """Phase 7 prep: repopulate in-memory maps from DB after restart."""
        async with self.db.session() as s:
            stmt = select(AgentInstanceORM).where(
                AgentInstanceORM.conversation_id == conversation_id
            )
            insts = (await s.execute(stmt)).scalars().all()
            for inst in insts:
                if inst.agent_type == "orchestrator":
                    self._orchestrators[conversation_id] = {
                        "hermes_session_id": inst.workspace_id or "",
                        "instance_id": inst.id,
                    }
                stmt2 = select(AgentRunORM).where(
                    AgentRunORM.agent_instance_id == inst.id,
                    AgentRunORM.status == "running",
                )
                for run in (await s.execute(stmt2)).scalars().all():
                    if run.hermes_run_id:
                        self._run_convo[run.hermes_run_id] = conversation_id
