"""Tools router — run a single tool inside a session.

This is the Phase 3 entry point used by:
  - the Phase 5 workflow runner (it calls `POST /sessions/{id}/workflow/run`
    which in turn iterates steps and calls the executor)
  - manual smoke testing from curl / frontend during Phase 6

Phase 5 will replace the simple workflow-run endpoint here with the
proper sequential runner + Pause/Resume/Stop support. The single-tool
endpoint stays.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from services.tool_executor import ToolExecutor
from services.tool_registry import list_tool_names
from services.workflow_service import WorkflowService


log = logging.getLogger(__name__)

router = APIRouter(tags=["tools"])


class ToolRunRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)


class ToolRunResponse(BaseModel):
    session_id: UUID
    tool_name: str
    status: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    duration_ms: int


class WorkflowRunResponse(BaseModel):
    session_id: UUID
    workflow_id: UUID
    step_count: int
    results: List[Dict[str, Any]]


def _executor(request: Request) -> ToolExecutor:
    return request.app.state.tool_executor


def _sessions_svc(request: Request):
    return request.app.state.session_service


def _workflows_svc(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


@router.get("/tools", response_model=List[str])
async def list_tools() -> List[str]:
    """Return the whitelist of tool names (MVP)."""
    return list_tool_names()


@router.post(
    "/sessions/{session_id}/tools/{tool_name}",
    response_model=ToolRunResponse,
)
async def run_tool(
    session_id: UUID,
    tool_name: str,
    body: ToolRunRequest,
    request: Request,
) -> ToolRunResponse:
    """Run a single tool against the host machine."""
    sessions = _sessions_svc(request)
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    executor: ToolExecutor = _executor(request)
    result = await executor.execute(
        session_id=session_id,
        step_id=None,
        tool_name=tool_name,
        params=body.params,
    )
    return ToolRunResponse(
        session_id=session_id,
        tool_name=tool_name,
        status=result["status"],
        output=result["output"],
        error=result["error"],
        duration_ms=result["duration_ms"],
    )


@router.post(
    "/sessions/{session_id}/workflow/run",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_200_OK,
)
async def run_workflow(
    session_id: UUID,
    request: Request,
) -> WorkflowRunResponse:
    """Run every step of the session's current workflow sequentially.

    Phase 5 will replace this with a proper runner that supports
    pause/resume/stop + per-step retry. For now we run all steps in
    a single async sequence and return the per-step results.
    """
    sessions = _sessions_svc(request)
    workflows = _workflows_svc(request)
    executor: ToolExecutor = _executor(request)

    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    workflow = await workflows.get_for_session(session_id)
    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="no workflow for this session",
        )

    results: List[Dict[str, Any]] = []
    for step in workflow.steps:
        # pydantic params from the workflow step.
        params = dict(step.params)
        # type_text / click_xy etc. were built by parse_intent;
        # we trust them since the workflow was validated at build time.
        result = await executor.execute(
            session_id=session_id,
            step_id=step.id,
            tool_name=step.tool_name,
            params=params,
        )
        results.append({
            "step_id": str(step.id),
            "tool_name": step.tool_name,
            "status": result["status"],
            "output": result["output"],
            "error": result["error"],
            "duration_ms": result["duration_ms"],
        })
        # Phase 5: honour user_paused / user_stopped here.

    return WorkflowRunResponse(
        session_id=session_id,
        workflow_id=workflow.workflow_id,
        step_count=len(workflow.steps),
        results=results,
    )
