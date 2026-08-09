"""
API V2 Production Workspace Router (Stage B — Production API Foundation).

Exposes durable endpoints for project metadata, workspace snapshots, canonical
command execution with idempotency & optimistic concurrency (revision_id),
and authorized media delivery.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_api.dependencies import get_video_production_uow
from windagent_core.domain.video_production.command_dispatcher import CommandDispatcher
from windagent_core.domain.video_production.query_service import ProductionQueryService
from windagent_core.domain.video_production.workspace import (
    WorkspaceCommandRequest,
    WorkspaceCommandStatus,
    WorkspaceCommandType,
)

router = APIRouter(prefix="/api/v2/video-production", tags=["production-workspace"])


class CommandRequestSchema(BaseModel):
    command_type: WorkspaceCommandType
    project_id: str
    target_revision_id: str
    entity_id: str
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    client_context: dict[str, Any] = Field(default_factory=dict)


@router.get("/projects/{project_id}", response_model=dict[str, Any])
async def get_project_detail(
    project_id: str,
    uow_factory=Depends(get_video_production_uow),
) -> dict[str, Any]:
    """Retrieve durable production project metadata."""
    async with uow_factory as uow:
        query_service = ProductionQueryService(uow)
        project = await query_service.get_project_detail(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "https://windagent.io/errors/project-not-found",
                    "title": "Project Not Found",
                    "status": 404,
                    "code": "PROJECT_NOT_FOUND",
                    "detail": f"Production project '{project_id}' does not exist.",
                },
            )
        return project


@router.get("/projects/{project_id}/workspace", response_model=dict[str, Any])
async def get_project_workspace_snapshot(
    project_id: str,
    revision_id: str | None = Query(None, description="Optional target revision ID"),
    uow_factory=Depends(get_video_production_uow),
) -> dict[str, Any]:
    """Retrieve consolidated workspace state snapshot for a project ID."""
    async with uow_factory as uow:
        query_service = ProductionQueryService(uow)
        snapshot = await query_service.get_workspace_snapshot(project_id, revision_id)

        if snapshot.get("error") == "STALE_REVISION":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "https://windagent.io/errors/stale-revision",
                    "title": "Stale Revision",
                    "status": 409,
                    "code": "REJECTED_STALE",
                    "detail": snapshot.get("message"),
                    "target_revision_id": revision_id,
                    "current_revision_id": snapshot.get("current_revision_id"),
                },
            )
        return snapshot


@router.get("/workspace/snapshot", response_model=dict[str, Any])
async def get_workspace_snapshot_by_query(
    project_id: str = Query(..., description="Target VideoProject ID"),
    revision_id: str | None = Query(None, description="Optional target revision ID"),
    uow_factory=Depends(get_video_production_uow),
) -> dict[str, Any]:
    """Retrieve consolidated workspace state snapshot query parameter endpoint."""
    return await get_project_workspace_snapshot(
        project_id=project_id, revision_id=revision_id, uow_factory=uow_factory
    )



@router.post("/commands", response_model=dict[str, Any])
@router.post("/workspace/commands", response_model=dict[str, Any])
async def execute_workspace_command(
    body: CommandRequestSchema,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    uow_factory=Depends(get_video_production_uow),
) -> dict[str, Any]:
    """Process mutating workspace actions with idempotency & revision validation."""
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "https://windagent.io/errors/missing-idempotency-key",
                "title": "Missing Idempotency Key",
                "status": 400,
                "code": "MISSING_IDEMPOTENCY_KEY",
                "detail": "X-Idempotency-Key header is required for canonical mutating commands.",
            },
        )

    cmd_request = WorkspaceCommandRequest(
        command_id=f"cmd_{uuid.uuid4().hex[:12]}",
        command_type=body.command_type,
        project_id=body.project_id,
        target_revision_id=body.target_revision_id,
        entity_id=body.entity_id,
        reason=body.reason,
        idempotency_key=x_idempotency_key.strip(),
        payload=body.payload,
        client_context=body.client_context,
    )

    async with uow_factory as uow:
        dispatcher = CommandDispatcher(uow)
        result = await dispatcher.dispatch(cmd_request)

        status_str = result.get("status")
        if status_str in (
            WorkspaceCommandStatus.REJECTED_STALE.value,
            WorkspaceCommandStatus.REJECTED_LOCKED.value,
            WorkspaceCommandStatus.IDEMPOTENCY_MISMATCH.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": f"https://windagent.io/errors/{status_str.lower()}",
                    "title": status_str,
                    "status": 409,
                    "code": status_str,
                    "detail": result.get("message"),
                    "target_revision_id": body.target_revision_id,
                    "current_revision_id": result.get("updated_revision_id"),
                    "current_sequence": result.get("current_sequence", 0),
                },
            )

        return result


@router.get("/workspace/media/{media_token}")
def get_authorized_media(media_token: str) -> dict[str, str]:
    """Deliver authorized media delivery token resolution (no raw file paths exposed)."""
    if not media_token.startswith("tok_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "type": "https://windagent.io/errors/invalid-media-token",
                "title": "Forbidden Media Access",
                "status": 403,
                "code": "FORBIDDEN_MEDIA_TOKEN",
                "detail": "Invalid or expired media token format.",
            },
        )
    return {
        "media_token": media_token,
        "content_type": "video/mp4",
        "status": "AUTHORIZED",
    }
