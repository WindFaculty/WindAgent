"""
FastAPI entrypoint for WindAgent Architecture V2 API (Phase 25 Cutover).
Uses canonical lifespan manager, ApplicationContainer composition root, RFC 7807 exception mapping for WindAgentError,
and registers all canonical V2 routers. API V1 has been permanently removed - returns 410 Gone.
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from windagent_core.domain.lifecycle import utc_now
from windagent_core.errors.exceptions import (
    WindAgentError, NotFoundError, PermissionDeniedError, ValidationError, DomainError
)
from windagent_core.version import (
    PRODUCT_VERSION,
    ARCHITECTURE_GENERATION,
    PROVIDER_PROTOCOL_VERSION,
    ARTIFACT_PROTOCOL_VERSION,
)
from windagent_api.lifespan import lifespan
from windagent_api.health import router as health_router
from windagent_api.routers.v2_sessions import router as v2_sessions_router
from windagent_api.routers.v2_tasks import router as v2_tasks_router
from windagent_api.routers.v2_runs import router as v2_runs_router
from windagent_api.routers.v2_workflows import router as v2_workflows_router
from windagent_api.routers.v2_events import v2_events_router
from windagent_api.routers.v2_events import v2_events_legacy_router
from windagent_api.routers.v2_providers import router as v2_providers_router
from windagent_api.routers.v2_tools import router as v2_tools_router
from windagent_api.routers.v2_permissions import router as v2_permissions_router
from windagent_api.routers.v2_artifacts import router as v2_artifacts_router
from windagent_api.routers.v2_memory import router as v2_memory_router
from windagent_api.routers.v2_plugins import router as v2_plugins_router
from windagent_api.routers.v2_skills import router as v2_skills_router
from windagent_api.routers.v2_evals import router as v2_evals_router
from windagent_api.routers.v2_observability import router as v2_observability_router
from windagent_api.routers.v2_browser import router as v2_browser_router
from windagent_api.routers.v2_production_workspace import router as v2_production_workspace_router
from windagent_api.routers.v2_screenplay_workspace import router as v2_screenplay_workspace_router
from windagent_api.routers.v2_assets import router as v2_assets_router
from windagent_api.routers.v2_collaboration import router as v2_collaboration_router
from windagent_api.routers.v2_conversations import router as v2_conversations_router
from windagent_api.routers.v2_conflict_recovery import router as v2_conflict_recovery_router

from windagent_api.routers.conversation_streams import router as conversation_streams_router
from windagent_api.routers.v3 import v3_router
from windagent_api.routers.v3.common import (
    CorrelationIdMiddleware,
    ApiProblemException,
    api_problem_exception_handler,
)
from windagent_api.routers.v3.studio.errors import studio_error_handler
from windagent_core.contracts.studio.errors import StudioError

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("windagent.api.main")

app = FastAPI(
    title="WindAgent API",
    description="Modular Monolith API Production Application with Unified V3 Foundation",
    version=PRODUCT_VERSION,
    lifespan=lifespan,
)

# Correlation ID tracing middleware (P2.5)
app.add_middleware(CorrelationIdMiddleware)

# CORS configuration for Web and Desktop Frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers Mapping WindAgentError to Structured JSON
@app.exception_handler(ApiProblemException)
async def v3_problem_exception_handler(request: Request, exc: ApiProblemException) -> JSONResponse:
    return await api_problem_exception_handler(request, exc)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "type": "https://windagent.io/errors/not-found",
            "title": "Resource Not Found",
            "status": 404,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_NOT_FOUND"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_exception_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "type": "https://windagent.io/errors/permission-denied",
            "title": "Permission Denied",
            "status": 403,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_PERMISSION_DENIED"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "type": "https://windagent.io/errors/validation-error",
            "title": "Validation Error",
            "status": 400,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_VALIDATION_FAILED"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(DomainError)
async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "https://windagent.io/errors/domain-error",
            "title": "Domain Error",
            "status": 422,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_DOMAIN_INVARIANT_VIOLATION"),
            "details": getattr(exc, "details", {}),
        },
    )


@app.exception_handler(StudioError)
async def studio_exception_handler(request: Request, exc: StudioError) -> JSONResponse:
    return studio_error_handler(request, exc)


@app.exception_handler(WindAgentError)
async def base_windagent_exception_handler(request: Request, exc: WindAgentError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "type": "https://windagent.io/errors/internal",
            "title": "WindAgent Internal Error",
            "status": 500,
            "detail": exc.message,
            "code": getattr(exc, "code", "WINDAGENT_ERR_INTERNAL"),
        },
    )


# Register Health Router
app.include_router(health_router)

ENABLE_V2_API = os.getenv("ENABLE_V2_API", "false").lower() == "true"

if ENABLE_V2_API:
    # Optional legacy fallback if explicitly enabled
    app.include_router(v2_sessions_router)
    app.include_router(v2_tasks_router)
    app.include_router(v2_runs_router)
    app.include_router(v2_workflows_router)
    app.include_router(v2_events_router)
    app.include_router(v2_events_legacy_router)
    app.include_router(v2_providers_router)
    app.include_router(v2_tools_router)
    app.include_router(v2_permissions_router)
    app.include_router(v2_artifacts_router)
    app.include_router(v2_memory_router)
    app.include_router(v2_plugins_router)
    app.include_router(v2_skills_router)
    app.include_router(v2_evals_router)
    app.include_router(v2_observability_router)
    app.include_router(v2_browser_router)
    app.include_router(v2_production_workspace_router)
    app.include_router(v2_screenplay_workspace_router)
    app.include_router(v2_assets_router)
    app.include_router(v2_collaboration_router)
    app.include_router(v2_conversations_router)
    app.include_router(v2_conflict_recovery_router)
else:
    # Phase 15 — API V2 Tombstone Handler - Returns 410 Gone for all retired /api/v2/* requests
    @app.api_route("/api/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
    async def api_v2_tombstone(request: Request, path: str):
        """
        API V2 has been permanently retired as per Phase 15 API V2 Retirement.
        Returns 410 Gone to indicate the resource is no longer available.
        """
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            headers={"Deprecation": "true"},
            content={
                "type": "https://windagent.io/errors/api-v2-retired",
                "title": "API V2 Retired",
                "status": 410,
                "detail": "API V2 has been permanently retired. Please use /api/v3/* endpoints.",
                "removal_date": "2026-08-17",
                "migration_guide": "https://windagent.io/docs/architecture-v3-migration",
                "available_endpoints": "/api/v3/*",
            },
        )

app.include_router(conversation_streams_router)

# Unified V3 Root Router (Phase 2-14 Foundation)
app.include_router(v3_router)


@app.websocket("/ws")
async def root_websocket_endpoint(websocket: WebSocket):
    """Canonical root WebSocket endpoint for RealtimeProvider events (Phase 6).

    Protocol:
    - initial ``{"type":"connected", ...}`` compatibility message;
    - JSON ``subscribe`` with non-empty ``aggregate_type`` / ``aggregate_id``
      and integer ``after_sequence >= 0`` (default 0);
    - ``subscribed`` control message, then replay events using the canonical
      event fields, then ``catchup_complete`` with the final cursor;
    - live pushes afterwards; ``unsubscribe`` acknowledged with ``unsubscribed``;
    - legacy raw ``ping`` and JSON ``{"type":"ping"}`` both return a pong;
    - malformed/unsupported messages receive a stable error envelope.
    """
    await websocket.accept()
    container = getattr(websocket.app.state, "container", None)
    hub = getattr(container, "realtime_hub", None) if container is not None else None
    if hub is None:
        await websocket.close(code=1011, reason="realtime hub unavailable")
        return
    await websocket.send_json({
        "type": "connected",
        "message": "WindAgent Realtime Connected",
        "timestamp": utc_now().isoformat(),
    })
    connection_id = f"conn_{uuid.uuid4().hex[:12]}"
    # Stream key ("aggregate_type:aggregate_id") -> current subscription id.
    # A repeated subscribe replaces the previous subscription in the hub, so
    # only the current id is tracked here; cleanup and unsubscribe by either
    # id or stream must target only the current subscription.
    subscription_ids: dict[str, str] = {}
    try:
        while True:
            raw = await websocket.receive_text()
            message = _parse_ws_message(raw)
            if message is None:
                if raw == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({
                        "type": "error",
                        "error": "invalid_json",
                        "message": "message must be valid JSON",
                    })
                continue
            msg_type = message.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "subscribe":
                validation_error = _validate_subscribe(message)
                if validation_error is not None:
                    await websocket.send_json({
                        "type": "error",
                        "error": "invalid_subscription",
                        "message": validation_error,
                    })
                    continue
                aggregate_type = str(message["aggregate_type"]).strip()
                aggregate_id = str(message["aggregate_id"]).strip()
                sub_id = await hub.subscribe(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    after_sequence=int(message.get("after_sequence", 0)),
                    sender=_canonical_sender(websocket),
                    connection_id=connection_id,
                )
                subscription_ids[f"{aggregate_type}:{aggregate_id}"] = sub_id
            elif msg_type == "unsubscribe":
                sub_id = message.get("subscription_id")
                if sub_id and sub_id in subscription_ids.values():
                    await hub.unsubscribe(sub_id)
                    for key, current in list(subscription_ids.items()):
                        if current == sub_id:
                            del subscription_ids[key]
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "subscription_id": sub_id,
                    })
                else:
                    # Frontend compatibility: the client identifies the stream
                    # by aggregate identity and does not retain subscription_id.
                    aggregate_type = message.get("aggregate_type")
                    aggregate_id = message.get("aggregate_id")
                    if (
                        isinstance(aggregate_type, str)
                        and aggregate_type.strip()
                        and isinstance(aggregate_id, str)
                        and aggregate_id.strip()
                    ):
                        stream_key = f"{aggregate_type.strip()}:{aggregate_id.strip()}"
                        current_sub_id = subscription_ids.get(stream_key)
                        if current_sub_id is not None:
                            removed = await hub.unsubscribe_stream(
                                connection_id=connection_id,
                                aggregate_type=aggregate_type.strip(),
                                aggregate_id=aggregate_id.strip(),
                            )
                            del subscription_ids[stream_key]
                            await websocket.send_json({
                                "type": "unsubscribed",
                                "subscription_id": (
                                    removed if removed is not None else current_sub_id
                                ),
                                "aggregate_type": aggregate_type.strip(),
                                "aggregate_id": aggregate_id.strip(),
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": "unknown_subscription",
                                "message": "no subscription for aggregate stream",
                            })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "error": "unknown_subscription",
                            "message": "unknown subscription_id",
                        })
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": "unsupported_message",
                    "message": f"unsupported message type: {msg_type!r}",
                })
    except WebSocketDisconnect:
        pass
    finally:
        for sub_id in subscription_ids.values():
            try:
                await hub.unsubscribe(sub_id)
            except Exception:
                pass
        try:
            await hub.disconnect(connection_id)
        except Exception:
            pass


def _parse_ws_message(raw: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON object message; returns None for non-JSON/non-object input."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _validate_subscribe(message: Dict[str, Any]) -> Optional[str]:
    """Validate a subscribe message; returns an error string or None."""
    aggregate_type = message.get("aggregate_type")
    aggregate_id = message.get("aggregate_id")
    after_sequence = message.get("after_sequence", 0)
    if not isinstance(aggregate_type, str) or not aggregate_type.strip():
        return "aggregate_type must be a non-empty string"
    if not isinstance(aggregate_id, str) or not aggregate_id.strip():
        return "aggregate_id must be a non-empty string"
    if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
        return "after_sequence must be an integer >= 0"
    return None


def _canonical_sender(websocket: WebSocket):
    """Sender that emits the canonical wire protocol for the root /ws endpoint."""

    async def send(message: Dict[str, Any]) -> None:
        if message.get("type") in ("subscribed", "catchup_complete"):
            await websocket.send_json(message)
        else:
            await websocket.send_json({
                k: v for k, v in message.items() if k not in ("is_replay", "metadata")
            })

    return send



# API V1 Tombstone Handler - Returns 410 Gone for all /api/v1/* requests
@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def api_v1_tombstone(request: Request, path: str):
    """
    API V1 has been permanently removed as per Architecture V2 cutover.
    This tombstone handler returns 410 Gone to indicate the resource is no longer available.
    """
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "type": "https://windagent.io/errors/api-v1-removed",
            "title": "API V1 Removed",
            "status": 410,
            "detail": "API V1 has been permanently removed. Please migrate to API V3.",
            "removal_date": "2026-07-25",
            "migration_guide": "https://windagent.io/docs/architecture-v3-migration",
            "available_endpoints": "/api/v3/*",
        },
    )


class ArchitectureResponse(BaseModel):
    architecture: str
    status: str
    version: str
    architecture_generation: str
    api_version: str
    provider_protocol_version: str
    artifact_protocol_version: str


@app.get("/internal/architecture", response_model=ArchitectureResponse)
async def internal_architecture() -> ArchitectureResponse:
    return ArchitectureResponse(
        architecture="V3",
        status="canonical_api_v3_production",
        version=PRODUCT_VERSION,
        architecture_generation=ARCHITECTURE_GENERATION,
        api_version="v3",
        provider_protocol_version=PROVIDER_PROTOCOL_VERSION,
        artifact_protocol_version=ARTIFACT_PROTOCOL_VERSION,
    )
