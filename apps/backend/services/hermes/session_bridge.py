"""Bridge for mapping WindAgent sessions to supervised Hermes API Server runs."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, update

from db.database import Database
from db.models import AgentORM, AgentSessionORM, PermissionRequestORM
from services.event_bus import EventBus
from services.hermes.api_client import HermesApiClient
from services.hermes.event_mapper import HermesEventTranslator

log = logging.getLogger(__name__)


class HermesSessionBridge:
    """Manages active runs, pulls SSE streams, translates, and publishes events."""

    def __init__(self, db: Database, client: HermesApiClient, event_bus: EventBus) -> None:
        self.db = db
        self.client = client
        self.event_bus = event_bus
        self.active_tasks: Dict[str, asyncio.Task] = {}
        
        # Keep track of generated permission UUIDs mapping: windagent_request_id -> hermes_approval_id
        # and hermes_approval_id -> windagent_request_id per run
        self.approval_mappings: Dict[str, Dict[str, str]] = {} # run_id -> {hermes_id: windagent_id}

    async def submit_message(
        self,
        *,
        windagent_session_id: str,
        agent_id: str,
        content: str,
        workspace_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a new run for a user message."""
        async with self.db.session() as session:
            # 1. Fetch the configured Agent
            stmt = select(AgentORM).where(AgentORM.id == agent_id)
            res = await session.execute(stmt)
            agent = res.scalar_one_or_none()
            if not agent:
                raise ValueError(f"Agent '{agent_id}' not found in registry")

            # 2. Check if there is an existing session mapping to reuse the conversation history
            stmt = select(AgentSessionORM).where(
                AgentSessionORM.windagent_session_id == windagent_session_id
            )
            res = await session.execute(stmt)
            agent_sess = res.scalar_one_or_none()

            hermes_session_id = None
            if agent_sess:
                hermes_session_id = agent_sess.hermes_session_id

            if not hermes_session_id:
                hermes_session_id = f"sess_{uuid.uuid4().hex}"

        # 3. Call start_run in Hermes API
        model_role = f"role:{agent.router_role}" if agent.router_role else "role:Coder"
        resp = await self.client.start_run(
            user_message=content,
            session_id=hermes_session_id,
            instructions=agent.system_prompt,
            model=model_role,
        )

        run_id = resp["run_id"]
        
        # 4. Save/update session bridge mapping
        async with self.db.session() as db_sess:
            if agent_sess:
                # Update current run_id and status
                stmt_up = (
                    update(AgentSessionORM)
                    .where(AgentSessionORM.windagent_session_id == windagent_session_id)
                    .values(
                        hermes_run_id=run_id,
                        hermes_session_id=hermes_session_id,
                        status="running",
                        workspace_root=workspace_root or agent.workspace_root,
                        router_role=agent.router_role,
                    )
                )
                await db_sess.execute(stmt_up)
            else:
                agent_sess = AgentSessionORM(
                    id=str(uuid.uuid4()),
                    windagent_session_id=windagent_session_id,
                    agent_id=agent_id,
                    runtime_type="hermes",
                    hermes_session_id=hermes_session_id,
                    hermes_run_id=run_id,
                    status="running",
                    workspace_root=workspace_root or agent.workspace_root,
                    router_role=agent.router_role,
                    started_at=datetime.now(timezone.utc),
                )
                db_sess.add(agent_sess)

        # 5. Spawn background task to stream events
        task = asyncio.create_task(
            self._stream_run(windagent_session_id, run_id),
            name=f"hermes-stream-{run_id}"
        )
        self.active_tasks[run_id] = task

        return {
            "run_id": run_id,
            "session_id": hermes_session_id,
            "status": "running"
        }

    async def stop_run(self, windagent_session_id: str) -> bool:
        """Call stop on the active run for the session."""
        async with self.db.session() as session:
            stmt = select(AgentSessionORM).where(
                AgentSessionORM.windagent_session_id == windagent_session_id
            )
            res = await session.execute(stmt)
            agent_sess = res.scalar_one_or_none()
            if not agent_sess or not agent_sess.hermes_run_id:
                return False
            
            run_id = agent_sess.hermes_run_id

        try:
            await self.client.stop_run(run_id)
            return True
        except Exception:
            log.exception("Failed to stop Hermes run %s", run_id)
            return False

    async def resolve_approval(self, windagent_session_id: str, windagent_request_id: UUID, granted: bool) -> bool:
        """Proxy decision to the corresponding Hermes approval request."""
        async with self.db.session() as session:
            # 1. Fetch request details
            stmt = select(PermissionRequestORM).where(
                PermissionRequestORM.windagent_request_id == str(windagent_request_id)
            )
            res = await session.execute(stmt)
            req = res.scalar_one_or_none()
            if not req or req.status != "pending":
                return False

            run_id = req.run_id
            hermes_approval_id = req.hermes_approval_id
            
            # Update status in db
            req.status = "granted" if granted else "denied"

        if not run_id or not hermes_approval_id:
            return False

        choice = "once" if granted else "deny"
        try:
            await self.client.submit_approval(run_id, choice)
            return True
        except Exception:
            log.exception("Failed to submit approval choice to Hermes")
            return False

    async def _stream_run(self, windagent_session_id: str, run_id: str) -> None:
        """Listen to SSE stream, map events, and publish to WebSocket bus."""
        log.info("Listening to SSE stream for run_id=%s", run_id)
        sequence = 1
        
        self.approval_mappings[run_id] = {}
        
        try:
            async for event in self.client.stream_run_events(run_id):
                # Check for approval request to cache ID mapping
                windagent_req_id = None
                if event.get("event") == "approval.request":
                    # Generate a new unique Request ID for WindAgent frontend
                    windagent_req_id = str(uuid.uuid4())
                    hermes_id = event.get("id") or event.get("tool") or "cmd"
                    self.approval_mappings[run_id][hermes_id] = windagent_req_id
                    
                    # Store in DB
                    async with self.db.session() as db_sess:
                        req_orm = PermissionRequestORM(
                            windagent_request_id=windagent_req_id,
                            hermes_approval_id=hermes_id,
                            session_id=windagent_session_id,
                            run_id=run_id,
                            risk_level="high" if "destructive" in str(event.get("tool")).lower() else "medium",
                            tool_name=event.get("tool") or "terminal",
                            arguments_redacted=str(event.get("command") or ""),
                            status="pending",
                        )
                        db_sess.add(req_orm)

                # Translate
                env = HermesEventTranslator.translate(
                    event=event,
                    windagent_session_id=windagent_session_id,
                    sequence=sequence,
                    windagent_request_id=windagent_req_id,
                )
                
                if env:
                    sequence += 1
                    # Publish event on the WebSocket bus for the session
                    await self.event_bus.publish(windagent_session_id, env)

                # Update session final status
                event_name = event.get("event")
                if event_name in ("run.completed", "run.failed", "run.cancelled"):
                    final_status = "completed"
                    if event_name == "run.failed":
                        final_status = "failed"
                    elif event_name == "run.cancelled":
                        final_status = "cancelled"

                    async with self.db.session() as db_sess:
                        stmt_up = (
                            update(AgentSessionORM)
                            .where(AgentSessionORM.hermes_run_id == run_id)
                            .values(
                                status=final_status,
                                finished_at=datetime.now(timezone.utc),
                                last_event_sequence=sequence,
                                error_message=event.get("error") if event_name == "run.failed" else None
                            )
                        )
                        await db_sess.execute(stmt_up)
                    break

        except Exception as e:
            log.exception("Error in SSE streaming task for run_id=%s", run_id)
            # Emit error to client
            from schemas.event import EventEnvelope
            error_env = EventEnvelope(
                event="error",
                data={"session_id": windagent_session_id, "message": f"Hermes event stream crashed: {e}"}
            )
            await self.event_bus.publish(windagent_session_id, error_env)
        finally:
            self.active_tasks.pop(run_id, None)
            self.approval_mappings.pop(run_id, None)
            log.info("Finished event streaming for run_id=%s", run_id)
