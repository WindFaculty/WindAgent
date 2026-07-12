"""Phase 6 — Worktree + integration-agent control surface.

Reads: list worktrees for a conversation, capture a worktree diff.
Control: trigger the integration-agent merge flow for a coding agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

log = logging.getLogger(__name__)

router = APIRouter(prefix="/worktrees", tags=["worktrees"])


def _svc(request: Request):
    return request.app.state.worktree_service


@router.get("/conversation/{conversation_id}")
async def list_worktrees(
    conversation_id: str, request: Request
) -> Dict[str, Any]:
    svc = _svc(request)
    rows = await svc.list_for_conversation(conversation_id)
    return {
        "conversation_id": conversation_id,
        "worktrees": [
            {
                "id": w.id,
                "agent_instance_id": w.agent_instance_id,
                "task_id": w.task_id,
                "branch": w.branch_name,
                "path": w.path,
                "status": w.status,
                "last_diff": w.last_diff_summary,
            }
            for w in rows
        ],
    }


@router.post("/{agent_instance_id}/diff")
async def capture_diff(
    agent_instance_id: str, request: Request
) -> Dict[str, Any]:
    svc = _svc(request)
    summary = await svc.capture_diff(agent_instance_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="no active worktree")
    return {"agent_instance_id": agent_instance_id, "diff": summary}


@router.post("/{agent_instance_id}/integrate")
async def integrate(
    agent_instance_id: str,
    request: Request,
    target_branch: str = Query("main"),
    strategy: str = Query("merge"),
) -> Dict[str, Any]:
    supervisor = request.app.state.hermes_supervisor
    try:
        result = await supervisor.integrate_agent(
            instance_id=agent_instance_id,
            target_branch=target_branch,
            strategy=strategy,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"agent_instance_id": agent_instance_id, **result}
