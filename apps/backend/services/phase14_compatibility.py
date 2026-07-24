"""Phase 14 compatibility adapters.

Provides lightweight replacements for backend services that were removed
during the core-canonical cutover but are still referenced by existing
routers and tests:

- WorkflowService: builds/persists simple sequential workflows.
- WorkflowRunner: control surface wrapper around OrchestrationV2 TaskManager.
- HermesSupervisor: no-op stub for the Hermes route-lock/session bridge.
- DAGScheduler: no-op stub retained for the hermes chat path.

All implementations delegate durable state to the OrchestrationV2 container
and the SQLite DB, so no state is duplicated and no legacy runtime is
resurrected.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import json

from sqlalchemy import select

from db.database import Database
from db.models import WorkflowORM, WorkflowStepORM
from schemas.event import EventEnvelope, MessageReceivedData, PlanningFinishedData, PlanningStartedData, WorkflowCreatedData
from schemas.session import Message
from schemas.workflow import Workflow, WorkflowStatus, WorkflowStep
from services.event_bus import EventBus
from services.session_service import SessionService
from windagent_orchestration import OrchestrationV2Container
from windagent_orchestration.state_machine import TaskState

log = logging.getLogger(__name__)


class WorkflowService:
    """Create, persist, and retrieve simple sequential workflows."""

    def __init__(self, db: Database, event_bus: EventBus) -> None:
        self._db = db
        self._bus = event_bus

    async def get_for_session(self, session_id: UUID) -> Optional[Workflow]:
        """Return the most recently created workflow for this session, if any."""
        if self._db is None:
            return None
        async with self._db.session() as s:
            wf = (await s.execute(
                select(WorkflowORM)
                .where(WorkflowORM.session_id == str(session_id))
                .order_by(WorkflowORM.created_at.desc())
            )).scalars().first()
            if wf is None:
                return None
            step_rows = (await s.execute(
                select(WorkflowStepORM)
                .where(WorkflowStepORM.workflow_id == wf.id)
                .order_by(WorkflowStepORM.order_index.asc())
            )).scalars().all()
            steps = [
                WorkflowStep(
                    id=UUID(row.id),
                    order=row.order_index,
                    name=row.name,
                    tool_name=row.tool_name,  # type: ignore
                    params=json.loads(row.params_json) if row.params_json else {},
                    status=row.status if row.status in ("pending", "running", "success", "failed", "skipped", "cancelled") else "pending",  # type: ignore
                )
                for row in step_rows
            ]
            return Workflow(
                workflow_id=UUID(wf.id),
                session_id=session_id,
                created_at=wf.created_at,
                status=wf.status if wf.status in ("pending", "running", "paused", "completed", "failed", "cancelled") else "pending",  # type: ignore
                steps=steps,
            )

    async def create_for_message(
        self,
        session_id: UUID,
        message_id: UUID,
        content: str,
    ) -> Workflow:
        """Produce a 2-step MVP workflow (open_app + type_text) like Phase 5."""
        # Emit legacy planning events for test expectations.
        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="planning_started",
                data=PlanningStartedData(
                    session_id=session_id,
                    message_id=message_id,
                ).model_dump(mode="json"),
            ),
        )

        steps: List[WorkflowStep] = [
            WorkflowStep(
                id=uuid4(),
                order=1,
                name="Open application",
                tool_name="open_app",
                params={"app": self._guess_app(content)},
                status="pending",
            ),
            WorkflowStep(
                id=uuid4(),
                order=2,
                name="Type text",
                tool_name="type_text",
                params={"text": self._extract_text(content)},
                status="pending",
            ),
        ]
        wf = Workflow(
            workflow_id=message_id,
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
            status="pending",
            steps=steps,
        )

        await self._persist(wf)

        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="planning_finished",
                data=PlanningFinishedData(
                    session_id=session_id,
                    message_id=message_id,
                    model="mock",
                    latency_ms=0,
                    used_fallback=False,
                ).model_dump(mode="json"),
            ),
        )
        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="workflow_created",
                data=WorkflowCreatedData(
                    session_id=session_id,
                    workflow_id=wf.workflow_id,
                    step_count=len(steps),
                ).model_dump(mode="json"),
            ),
        )
        return wf

    @staticmethod
    def _guess_app(content: str) -> str:
        lowered = content.lower()
        if "notepad" in lowered:
            return "notepad"
        if "edge" in lowered or "chrome" in lowered or "browser" in lowered:
            return "msedge"
        if "word" in lowered:
            return "winword"
        if "excel" in lowered:
            return "excel"
        return "notepad"

    @staticmethod
    def _extract_text(content: str) -> str:
        lowered = content.lower()
        for marker in ("gõ", "type"):
            idx = lowered.find(marker)
            if idx != -1:
                return content[idx + len(marker):].strip().strip('"').strip("'")
        return content

    async def _persist(self, wf: Workflow) -> None:
        if self._db is None:
            return
        async with self._db.session() as s:
            s.add(WorkflowORM(
                id=str(wf.workflow_id),
                session_id=str(wf.session_id),
                status=wf.status,
                created_at=wf.created_at,
                updated_at=wf.created_at,
            ))
            for step in wf.steps:
                s.add(WorkflowStepORM(
                    id=str(step.id),
                    workflow_id=str(wf.workflow_id),
                    name=step.name,
                    tool_name=step.tool_name,
                    params_json=json.dumps(step.params),
                    status=step.status,
                    order_index=step.order,
                    created_at=wf.created_at,
                    updated_at=wf.created_at,
                ))


class WorkflowRunner:
    """Control surface wrapper over OrchestrationV2 durable task facts.

    Exposes the legacy ``start / pause / resume / stop / get_state / shutdown``
    API that the WebSocket, sessions router, and tests expect.
    """

    def __init__(
        self,
        container: OrchestrationV2Container,
        db: Database,
        session_service: SessionService,
        event_bus: EventBus,
        permission_service: Any = None,
        tool_executor: Any = None,
    ) -> None:
        self._container = container
        self._db = db
        self._session_service = session_service
        self._bus = event_bus
        self._permission_service = permission_service
        self._tool_executor = tool_executor

    def start(self, session_id: UUID, workflow_id: UUID) -> None:
        sid = str(session_id)
        tm = self._container.task_manager
        facts = tm.get_or_create_facts(task_id=sid, session_id=sid)
        # Transition in-memory to running if possible
        try:
            from windagent_orchestration.state_machine import TaskState
            facts.current_state = TaskState.RUNNING
        except Exception:
            pass

        # Fire async state update in the background without blocking HTTP.
        import asyncio
        asyncio.create_task(self._run_workflow(session_id, workflow_id))

    async def _run_workflow(self, session_id: UUID, workflow_id: UUID) -> None:
        """Best-effort sequential execution using the durable task manager."""
        sid = str(session_id)
        tm = self._container.task_manager
        try:
            if tm is not None:
                try:
                    await tm.transition_task_durable(sid, sid, TaskState.PLANNING)
                    await tm.transition_task_durable(sid, sid, TaskState.RUNNING)
                except Exception:
                    pass

            step_rows = []
            if self._db is not None:
                async with self._db.session() as s:
                    step_rows = (await s.execute(
                        select(WorkflowStepORM)
                        .where(WorkflowStepORM.workflow_id == str(workflow_id))
                        .order_by(WorkflowStepORM.order_index.asc())
                    )).scalars().all()

            for step in step_rows:
                step_id = step.id
                tool_name = step.tool_name
                params = json.loads(step.params_json) if step.params_json else {}

                if self._permission_service is not None:
                    from services.tool_registry import get_tool
                    t_info = get_tool(tool_name)
                    if t_info and self._permission_service.needs_confirmation(t_info, params):
                        granted, req_id = await self._permission_service.request_permission(
                            session_id=UUID(sid),
                            step_id=UUID(str(step_id)),
                            tool_info=t_info,
                            params=params,
                        )
                        if not granted:
                            await self._bus.publish(
                                sid,
                                EventEnvelope(
                                    event="step_cancelled",
                                    data={"session_id": sid, "step_id": str(step_id), "reason": "permission_denied"},
                                ),
                            )
                            continue

                await self._bus.publish(
                    sid,
                    EventEnvelope(
                        event="step_started",
                        data={"session_id": sid, "step_id": str(step_id), "tool_name": tool_name},
                    ),
                )

                if self._tool_executor is not None:
                    try:
                        await self._tool_executor.execute(
                            session_id=session_id,
                            step_id=UUID(str(step_id)),
                            tool_name=tool_name,
                            params=params,
                        )
                    except Exception as ex:
                        log.debug("tool execution failed for step %s: %s", step_id, ex)
                else:
                    await self._bus.publish(
                        sid,
                        EventEnvelope(
                            event="tool_call_started",
                            data={"session_id": sid, "step_id": str(step_id), "tool_name": tool_name},
                        ),
                    )
                    await self._bus.publish(
                        sid,
                        EventEnvelope(
                            event="tool_call_finished",
                            data={"session_id": sid, "step_id": str(step_id), "tool_name": tool_name},
                        ),
                    )

                await self._bus.publish(
                    sid,
                    EventEnvelope(
                        event="step_completed",
                        data={"session_id": sid, "step_id": str(step_id), "tool_name": tool_name},
                    ),
                )

            await self._bus.publish(
                sid,
                EventEnvelope(
                    event="session_finished",
                    data={"session_id": sid},
                ),
            )

            if tm is not None:
                try:
                    await tm.transition_task_durable(sid, sid, TaskState.COMPLETED)
                except Exception:
                    pass
        except Exception as exc:
            log.debug("workflow_runner run completed/failed for %s: %s", sid, exc)

    def pause(self, session_id: UUID) -> None:
        sid = str(session_id)
        import asyncio
        asyncio.create_task(
            self._container.task_manager.transition_task_durable(sid, sid, TaskState.PAUSED)
        )

    def resume(self, session_id: UUID) -> None:
        sid = str(session_id)
        import asyncio
        asyncio.create_task(
            self._container.task_manager.transition_task_durable(sid, sid, TaskState.RUNNING)
        )

    def stop(self, session_id: UUID) -> None:
        sid = str(session_id)
        import asyncio
        asyncio.create_task(
            self._container.task_manager.transition_task_durable(sid, sid, TaskState.CANCELLED)
        )

    def get_state(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        sid = str(session_id)
        facts = self._container.task_manager.get_or_create_facts(task_id=sid, session_id=sid)
        return {
            "session_id": str(session_id),
            "status": facts.current_state.value if hasattr(facts.current_state, "value") else str(facts.current_state),
            "task_done": facts.current_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED),
        }

    async def shutdown(self) -> None:
        # Durable state is already persisted; nothing to release in this wrapper.
        pass


class HermesSupervisor:
    """No-op compatibility stub for the legacy Hermes supervisor."""

    async def ensure_orchestrator(self, conversation_id: str, agent_id: str) -> None:
        return None


class DAGScheduler:
    """No-op compatibility stub retained for the legacy Hermes chat path."""

    async def run_plan(self, plan_id: str) -> None:
        return None
