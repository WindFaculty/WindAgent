"""Phase 5 — Sequential workflow runner with Pause / Resume / Stop / Retry.

State machine (per docs/event_protocol.md §"Phase 5"):

  session.status / workflow.status:
      idle -> planning -> running -> (paused -> running) -> completed
                                                 -> failed
                                                 -> cancelled

  step.status:
      pending -> running -> success
                       -> failed
      pending -> skipped / cancelled (when stop is requested mid-flight)

The runner:
  - Holds one asyncio.Task per session_id (dict keyed by session_id).
  - Honors `paused` (boolean flag) — runner spins on a short sleep loop while
    paused, so it does not block the event loop.
  - Honors `stop_requested` — once set, the loop breaks and remaining steps
    are marked `cancelled`. The flag is sticky for the current run; new runs
    (retry) start fresh.
  - On tool failure: emits `step_failed`, marks the workflow `failed`, halts.
    The user can then `retry` which spawns a fresh task starting at the
    failed step.
  - Emits `session_finished` with the final_status when the loop exits,
    regardless of whether it completed, was stopped, or failed.

Every state transition is published through the EventBus, which the
event_hooks mirror to `execution_events` (Phase 2 persistence).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from schemas.event import (
    EventEnvelope,
    SessionFinishedData,
    StepCompletedData,
    StepErrorInfo,
    StepFailedData,
    StepStartedData,
)
from schemas.workflow import Workflow, WorkflowStep
from services.event_bus import EventBus
from services.permission_service import PermissionService
from services.session_service import SessionService
from services.tool_executor import ToolExecutor
from services.tool_registry import get_tool
from services.workflow_service import WorkflowService


log = logging.getLogger(__name__)


# Tunables — kept tiny so unit tests stay fast.
_PAUSE_POLL_INTERVAL = 0.02  # seconds the runner sleeps while paused


# ---------- Per-session runtime state ----------

@dataclass
class _RunState:
    session_id: UUID
    workflow_id: UUID
    task: Optional[asyncio.Task] = None
    paused: bool = False
    stop_requested: bool = False
    current_step_index: int = 0  # index of the step being executed
    last_failed_step_id: Optional[UUID] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    final_status: Optional[str] = None  # completed / failed / cancelled


# ---------- Runner ----------

class WorkflowRunner:
    """Owns the asyncio tasks that execute workflows step by step.

    One instance per FastAPI app (stored on app.state.workflow_runner).
    Thread-affine to the event loop on which it was constructed.
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        executor: ToolExecutor,
        session_service: SessionService,
        workflow_service: WorkflowService,
        permission_service: Optional[PermissionService] = None,
    ) -> None:
        self._bus = event_bus
        self._executor = executor
        self._sessions = session_service
        self._workflows = workflow_service
        self._permissions = permission_service
        self._states: Dict[UUID, _RunState] = {}

    # ---------- Public control surface ----------

    def start(self, session_id: UUID, workflow_id: UUID) -> bool:
        """Start a fresh runner task. Returns False if already running."""
        existing = self._states.get(session_id)
        if existing is not None and existing.task is not None and not existing.task.done():
            log.warning(
                "start: session=%s already has a live runner task; ignoring",
                session_id,
            )
            return False

        state = _RunState(
            session_id=session_id,
            workflow_id=workflow_id,
            started_at=time.perf_counter(),
        )
        state.task = asyncio.create_task(
            self._run(session_id, workflow_id, start_index=0),
            name=f"workflow-runner-{session_id}",
        )
        self._states[session_id] = state
        return True

    def pause(self, session_id: UUID) -> bool:
        state = self._states.get(session_id)
        if state is None or state.task is None or state.task.done():
            return False
        if state.final_status is not None:
            return False  # already finished
        state.paused = True
        return True

    def resume(self, session_id: UUID) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        state.paused = False
        return True

    def stop(self, session_id: UUID) -> bool:
        state = self._states.get(session_id)
        if state is None or state.task is None or state.task.done():
            return False
        state.stop_requested = True
        state.paused = False  # unblock so the loop sees the flag quickly
        return True

    def retry(self, session_id: UUID) -> bool:
        """Re-run the workflow from the failed step (or from start if no
        failure recorded). Returns True if a new task was spawned."""
        state = self._states.get(session_id)
        if state is None:
            return False
        if state.task is not None and not state.task.done():
            # Live task — stop it first, then retry.
            state.stop_requested = True
            state.paused = False

        # Fresh state for the retry — same workflow, but reset position
        # and flags so the new task starts cleanly.
        new_state = _RunState(
            session_id=session_id,
            workflow_id=state.workflow_id,
            started_at=time.perf_counter(),
            current_step_index=state.current_step_index,
        )
        new_state.task = asyncio.create_task(
            self._run(
                session_id,
                state.workflow_id,
                start_index=state.current_step_index,
            ),
            name=f"workflow-runner-retry-{session_id}",
        )
        self._states[session_id] = new_state
        return True

    def get_state(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """Return a serialisable snapshot of the runner state, or None."""
        state = self._states.get(session_id)
        if state is None:
            return None
        return {
            "session_id": str(state.session_id),
            "workflow_id": str(state.workflow_id),
            "paused": state.paused,
            "stop_requested": state.stop_requested,
            "current_step_index": state.current_step_index,
            "last_failed_step_id": (
                str(state.last_failed_step_id) if state.last_failed_step_id else None
            ),
            "task_done": state.task.done() if state.task else True,
            "final_status": state.final_status,
        }

    async def shutdown(self) -> None:
        """Cancel every live runner task. Called from FastAPI lifespan exit."""
        for state in list(self._states.values()):
            state.stop_requested = True
            state.paused = False
            if state.task is not None and not state.task.done():
                state.task.cancel()
        # Give cancelled tasks a moment to unwind.
        for state in list(self._states.values()):
            if state.task is not None:
                try:
                    await asyncio.wait_for(state.task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                    pass

    # ---------- Main loop ----------

    async def _run(
        self,
        session_id: UUID,
        workflow_id: UUID,
        *,
        start_index: int,
    ) -> None:
        state = self._states[session_id]
        workflow = await self._workflows.get_for_session(session_id)
        if workflow is None:
            log.error("runner: workflow %s missing for session %s", workflow_id, session_id)
            state.final_status = "failed"
            return

        # Mark workflow + session as running before the first step.
        await self._workflows.update_status(session_id, "running", workflow_id=workflow_id)
        await self._sessions.update_status(session_id, "running")

        final_status = "completed"
        steps: List[WorkflowStep] = list(workflow.steps)

        try:
            for i in range(start_index, len(steps)):
                step = steps[i]
                state.current_step_index = i

                # --- Stop check (highest priority) ---
                if state.stop_requested:
                    await self._workflows.update_step_status(step.id, "cancelled")
                    final_status = "cancelled"
                    break

                # --- Pause loop ---
                while state.paused and not state.stop_requested:
                    await asyncio.sleep(_PAUSE_POLL_INTERVAL)

                if state.stop_requested:
                    await self._workflows.update_step_status(step.id, "cancelled")
                    final_status = "cancelled"
                    break

                # --- Emit step_started ---
                await self._bus.publish(
                    str(session_id),
                    EventEnvelope(
                        event="step_started",
                        data=StepStartedData(
                            session_id=session_id,
                            workflow_id=workflow_id,
                            step_id=step.id,
                            step_name=step.name,
                            tool_name=step.tool_name,
                            order=step.order,
                        ).model_dump(mode="json"),
                    ),
                )
                await self._workflows.update_step_status(step.id, "running")

                # --- Phase 7 permission gate ---
                denied_reason = await self._gate_permission(
                    session_id=session_id,
                    step_id=step.id,
                    tool_name=step.tool_name,
                    params=dict(step.params),
                )
                if denied_reason is not None:
                    # User denied (or timed out) — mark step cancelled and
                    # continue with the next step. Workflow does not fail.
                    log.info(
                        "runner: step %s cancelled by permission gate (%s)",
                        step.id, denied_reason,
                    )
                    continue

                # --- Execute the tool ---
                step_start = time.perf_counter()
                result = await self._executor.execute(
                    session_id=session_id,
                    step_id=step.id,
                    tool_name=step.tool_name,
                    params=dict(step.params),
                )
                step_duration_ms = int((time.perf_counter() - step_start) * 1000)

                if result["status"] == "success":
                    await self._bus.publish(
                        str(session_id),
                        EventEnvelope(
                            event="step_completed",
                            data=StepCompletedData(
                                session_id=session_id,
                                workflow_id=workflow_id,
                                step_id=step.id,
                                duration_ms=step_duration_ms,
                            ).model_dump(mode="json"),
                        ),
                    )
                    await self._workflows.update_step_status(step.id, "success")
                else:
                    err = result.get("error") or {
                        "type": "tool_error",
                        "message": "tool reported failure",
                        "code": "TOOL_FAILED",
                    }
                    await self._bus.publish(
                        str(session_id),
                        EventEnvelope(
                            event="step_failed",
                            data=StepFailedData(
                                session_id=session_id,
                                workflow_id=workflow_id,
                                step_id=step.id,
                                error=StepErrorInfo(**err),
                            ).model_dump(mode="json"),
                        ),
                    )
                    await self._workflows.update_step_status(step.id, "failed")
                    state.last_failed_step_id = step.id
                    final_status = "failed"
                    break
        except asyncio.CancelledError:
            final_status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("runner: unhandled exception for session %s", session_id)
            final_status = "failed"
        finally:
            total_ms = int(
                (time.perf_counter() - (state.started_at or time.perf_counter())) * 1000
            )
            state.final_status = final_status
            state.finished_at = time.perf_counter()

            # Persist + announce final workflow/session status.
            await self._workflows.update_status(
                session_id, final_status, workflow_id=workflow_id
            )
            await self._sessions.update_status(session_id, final_status)
            await self._bus.publish(
                str(session_id),
                EventEnvelope(
                    event="session_finished",
                    data=SessionFinishedData(
                        session_id=session_id,
                        workflow_id=workflow_id,
                        final_status=final_status,  # type: ignore[arg-type]
                        total_duration_ms=total_ms,
                    ).model_dump(mode="json"),
                ),
            )
            log.info(
                "runner: session=%s workflow=%s finished status=%s duration_ms=%d",
                session_id,
                workflow_id,
                final_status,
                total_ms,
            )

    # ---------- Phase 7: permission gate helper ----------

    async def _gate_permission(
        self,
        *,
        session_id: UUID,
        step_id: UUID,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Optional[str]:
        """Return None if execution should proceed.

        Return a short reason string if execution must be skipped
        (user denied or timed out). In that case the runner marks the
        step cancelled and moves on.

        If no PermissionService is wired, allow everything.
        """
        if self._permissions is None:
            return None
        try:
            tool_info = get_tool(tool_name)
        except KeyError:
            # Whitelist violation — should be impossible because the
            # planner + workflow build both validate. Be defensive.
            log.error(
                "permission gate: tool %r not in registry; allowing "
                "runner to fail it downstream",
                tool_name,
            )
            return None
        if not self._permissions.needs_confirmation(tool_info, params):
            return None
        granted, _ = await self._permissions.request_permission(
            session_id=session_id,
            step_id=step_id,
            tool_info=tool_info,
            params=params,
        )
        if granted:
            return None
        # Denied — mark the step cancelled so the workflow row reflects it.
        await self._workflows.update_step_status(step_id, "cancelled")
        return "user_denied"