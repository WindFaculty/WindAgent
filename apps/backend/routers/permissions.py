"""Phase 7 — Permissions router.

Two endpoints:

  POST /permissions/{request_id}/decide
      Body: {"decision": "granted" | "denied"}
      Effect: resolves the pending permission request, emits the
      permission_granted/denied event via the EventBus.

  GET /permissions/config
      Returns the current PermissionConfig as JSON.

  PATCH /permissions/config
      Update one or more fields of PermissionConfig.

A permission request is created by the WorkflowRunner via
PermissionService.request_permission() — the client receives the
`request_id` in the `permission_request` event payload.
"""
from __future__ import annotations

from typing import Any, Dict, Literal
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel, Field

from services.permission_service import PermissionService


router = APIRouter(prefix="/permissions", tags=["permissions"])


def _permissions(request: Request) -> PermissionService:
    return request.app.state.permission_service


class DecisionRequest(BaseModel):
    decision: Literal["granted", "denied"]


@router.post(
    "/{request_id}/decide",
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_permission(
    request_id: UUID,
    body: DecisionRequest,
    request: Request,
) -> Dict[str, Any]:
    svc = _permissions(request)
    granted = body.decision == "granted"
    resolved = await svc.resolve_permission(
        request_id, granted=granted
    )
    if not resolved:
        # Unknown / already-resolved / timed-out request_id.
        raise HTTPException(
            status_code=404,
            detail=(
                f"no pending permission request with id {request_id} "
                f"(already resolved or expired)"
            ),
        )
    return {
        "request_id": str(request_id),
        "decision": body.decision,
        "status": "resolved",
    }


@router.get("/config")
async def get_permission_config(request: Request) -> Dict[str, Any]:
    svc = _permissions(request)
    return svc.config_dict()


class ConfigPatch(BaseModel):
    safe_mode: bool | None = None
    confirm_before_type: bool | None = None
    confirm_before_click: bool | None = None
    type_text_length_threshold: int | None = Field(default=None, ge=1, le=10_000)


@router.patch("/config")
async def patch_permission_config(
    body: ConfigPatch,
    request: Request,
) -> Dict[str, Any]:
    svc = _permissions(request)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        svc.update_config(**updates)
    return svc.config_dict()