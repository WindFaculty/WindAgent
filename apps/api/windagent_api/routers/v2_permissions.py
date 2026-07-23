"""
API V2 Permissions endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/permissions", tags=["Permissions V2"])


class EvaluatePermissionRequest(BaseModel):
    action: str
    target: str


class PermissionEvaluationResponse(BaseModel):
    allowed: bool
    requires_approval: bool
    reason: str


@router.post("/evaluate", response_model=PermissionEvaluationResponse)
async def evaluate_permission(req: EvaluatePermissionRequest) -> PermissionEvaluationResponse:
    if req.action in ("read_file", "view_file", "grep_search"):
        return PermissionEvaluationResponse(allowed=True, requires_approval=False, reason="Read-only action allowed")
    elif req.action in ("write_file", "run_command"):
        return PermissionEvaluationResponse(allowed=True, requires_approval=True, reason="Modifying action requires explicit policy check")
    return PermissionEvaluationResponse(allowed=False, requires_approval=False, reason="Unknown action denied by default")
