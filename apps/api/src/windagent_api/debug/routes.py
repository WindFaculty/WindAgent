"""Debug routes: HTTP → DTO → Command/QueryBus → response mapper."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from windagent.kernel.types.json import thaw_json
from windagent.platform.commands import CommandBus
from windagent.platform.jobs import JobRecord
from windagent.platform.observability import current_operation_context
from windagent.platform.queries import QueryBus
from windagent.platform.realtime import RealtimeHub

from ..auth import get_principal
from ..middleware import get_request_context
from .contracts import CancelDebugJob, GetDebugJob, SubmitDebugJob


class DebugJobRequest(BaseModel):
    """Transport DTO; construction rules live in the handler, not here."""

    job_type: str = "debug.echo"
    payload: dict[str, object] = Field(default_factory=dict)
    priority: int = 0
    max_attempts: int = Field(default=3, ge=1)
    timeout_s: float | None = Field(default=None, gt=0)
    deadline: datetime | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None


def create_debug_jobs_router(*, include_events: bool) -> APIRouter:
    """Build the opt-in debug surface; production apps never mount it."""
    router = APIRouter(prefix="/debug/jobs", tags=["debug-jobs"])

    @router.post("")
    async def submit_job(request: DebugJobRequest, http_request: Request) -> JSONResponse:
        command_bus = cast(CommandBus, http_request.app.state.command_bus)
        request_context = get_request_context(http_request)
        operation_context = current_operation_context()
        principal = get_principal(http_request)
        result = await command_bus.dispatch(
            SubmitDebugJob(
                request.job_type,
                request.payload,
                priority=request.priority,
                max_attempts=request.max_attempts,
                timeout_s=request.timeout_s,
                deadline=request.deadline,
                correlation_id=(
                    request.correlation_id or str(request_context.correlation_id)
                ),
                causation_id=(
                    request.causation_id
                    or (
                        str(request_context.causation_id)
                        if request_context.causation_id is not None
                        else None
                    )
                ),
                trace_id=(
                    operation_context.trace_id
                    if operation_context is not None
                    else request_context.trace_id
                ),
                actor_id=(
                    str(principal.actor_id) if principal.actor_id is not None else None
                ),
                idempotency_key=request.idempotency_key,
            )
        )
        return JSONResponse(
            {
                "job_id": result.job_id,
                "status": "accepted",
                "deduplicated": result.deduplicated,
            },
            status_code=202,
        )

    @router.get("/{job_id}")
    async def get_job(job_id: str, http_request: Request) -> JSONResponse:
        query_bus = cast(QueryBus, http_request.app.state.query_bus)
        record = await query_bus.ask(GetDebugJob(job_id))
        return JSONResponse(_record_to_dict(record))

    @router.post("/{job_id}/cancel")
    async def cancel_job(job_id: str, http_request: Request) -> JSONResponse:
        command_bus = cast(CommandBus, http_request.app.state.command_bus)
        await command_bus.dispatch(CancelDebugJob(job_id))
        return JSONResponse(
            {"job_id": job_id, "cancellation_requested": True}, status_code=202
        )

    if include_events:

        @router.websocket("/events")
        async def job_events(websocket: WebSocket) -> None:
            hub = cast(RealtimeHub, websocket.app.state.realtime_hub)
            raw_after = websocket.query_params.get("after", "0")
            try:
                after = int(raw_after)
                subscription = await hub.subscribe(after=after)
            except ValueError:
                await websocket.close(
                    code=1008, reason="after must be a non-negative integer"
                )
                return
            await websocket.accept()
            try:
                while True:
                    message = await subscription.next()
                    await websocket.send_json(
                        {
                            "position": message.position,
                            "event": message.event.to_dict(),
                        }
                    )
            except WebSocketDisconnect:
                pass
            finally:
                await subscription.unsubscribe()

    return router


def _record_to_dict(record: JobRecord) -> dict[str, object]:
    envelope = record.envelope
    return {
        "job_id": str(envelope.id),
        "job_type": envelope.job_type,
        "version": int(envelope.version),
        "status": record.status.value,
        "priority": envelope.priority,
        "attempt": envelope.attempt,
        "max_attempts": envelope.max_attempts,
        "timeout_s": envelope.timeout_s,
        "deadline": envelope.deadline.isoformat() if envelope.deadline is not None else None,
        "available_at": record.available_at.isoformat(),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at is not None else None
        ),
        "cancellation_requested": record.cancellation_requested,
        "result": thaw_json(record.result) if record.result is not None else None,
        "error": record.error,
    }
