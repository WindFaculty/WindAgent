"""
API V2 Permissions endpoints for WindAgent Architecture V2 (Phase 25 Cutover).
Endpoints for evaluating, listing, and auditing permission requests via PermissionEngine.
"""

from __future__ import annotations
from typing import List
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


class PermissionPolicyResponse(BaseModel):
    action: str
    risk_level: str
    requires_approval: bool


@router.get("", response_model=List[PermissionPolicyResponse])
async def list_permissions() -> List[PermissionPolicyResponse]:
    return [
        PermissionPolicyResponse(action="read_file", risk_level="read_only", requires_approval=False),
        PermissionPolicyResponse(action="write_file", risk_level="workspace_write", requires_approval=True),
        PermissionPolicyResponse(action="exec_shell", risk_level="process_execution", requires_approval=True),
    ]


@router.post("/evaluate", response_model=PermissionEvaluationResponse)
async def evaluate_permission(req: EvaluatePermissionRequest) -> PermissionEvaluationResponse:
    if req.action in ("read_file", "view_file", "grep_search"):
        return PermissionEvaluationResponse(allowed=True, requires_approval=False, reason="Read-only action allowed")
    elif req.action in ("write_file", "run_command", "exec_shell"):
        return PermissionEvaluationResponse(allowed=True, requires_approval=True, reason="Modifying action requires explicit policy check")
    return PermissionEvaluationResponse(allowed=False, requires_approval=False, reason="Unknown action denied by default")
