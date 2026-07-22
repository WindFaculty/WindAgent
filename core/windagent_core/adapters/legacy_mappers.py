"""
Compatibility Mappers between legacy backend Pydantic schemas/dicts and V2 Domain Objects.
Enables seamless conversion across V1 <-> V2 architecture boundaries.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from windagent_core.domain.types import (
    SessionId, WorkflowId, StepId, RunId
)
from windagent_core.domain.models import (
    Session, SessionStatus, WorkflowRun, WorkflowStep, WorkflowStatus, StepStatus
)


def legacy_session_dict_to_domain(legacy_dict: Dict[str, Any]) -> Session:
    """Converts legacy ChatSession dictionary/schema to V2 Session domain model."""
    raw_id = legacy_dict.get("id") or legacy_dict.get("session_id")
    session_id = SessionId(raw_id) if raw_id else SessionId.generate()
    
    created_at = legacy_dict.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)

    updated_at = legacy_dict.get("updated_at")
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)
    elif not isinstance(updated_at, datetime):
        updated_at = created_at

    status_str = str(legacy_dict.get("status", "idle")).lower()
    try:
        status = SessionStatus(status_str)
    except ValueError:
        status = SessionStatus.IDLE

    return Session(
        id=session_id,
        created_at=created_at,
        updated_at=updated_at,
        status=status,
        title=legacy_dict.get("title"),
        agent_id=legacy_dict.get("agent_id"),
        workspace_root=legacy_dict.get("workspace_root"),
    )


def domain_session_to_legacy_dict(session: Session) -> Dict[str, Any]:
    """Converts V2 Session domain model to legacy ChatSession dictionary format."""
    return {
        "id": str(session.id),
        "session_id": str(session.id),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "status": session.status.value,
        "title": session.title,
        "agent_id": session.agent_id,
        "workspace_root": session.workspace_root,
    }


def legacy_step_dict_to_domain(step_dict: Dict[str, Any]) -> WorkflowStep:
    """Converts legacy WorkflowStep dictionary to V2 WorkflowStep domain model."""
    raw_id = step_dict.get("id") or step_dict.get("step_id")
    step_id = StepId(raw_id) if raw_id else StepId.generate()
    order = int(step_dict.get("order", 1))
    name = str(step_dict.get("name", f"Step-{order}"))
    tool_name = str(step_dict.get("tool_name", "wait"))
    params = step_dict.get("params", {}) or step_dict.get("params_json", {})
    
    status_str = str(step_dict.get("status", "pending")).lower()
    try:
        status = StepStatus(status_str)
    except ValueError:
        status = StepStatus.PENDING

    return WorkflowStep(
        id=step_id,
        order=order,
        name=name,
        tool_name=tool_name,
        params=params,
        status=status,
        result=step_dict.get("result"),
        error=step_dict.get("error"),
    )


def domain_step_to_legacy_dict(step: WorkflowStep) -> Dict[str, Any]:
    """Converts V2 WorkflowStep domain model to legacy dictionary format."""
    return {
        "id": str(step.id),
        "order": step.order,
        "name": step.name,
        "tool_name": step.tool_name,
        "params": step.params,
        "status": step.status.value,
        "result": step.result,
        "error": step.error,
    }


def legacy_workflow_dict_to_domain(wf_dict: Dict[str, Any]) -> WorkflowRun:
    """Converts legacy Workflow dictionary to V2 WorkflowRun domain model."""
    raw_wf_id = wf_dict.get("workflow_id") or wf_dict.get("id")
    wf_id = WorkflowId(raw_wf_id) if raw_wf_id else WorkflowId.generate()
    raw_run_id = wf_dict.get("run_id") or raw_wf_id
    run_id = RunId(raw_run_id) if raw_run_id else RunId.generate()
    
    raw_session_id = wf_dict.get("session_id")
    session_id = SessionId(raw_session_id) if raw_session_id else SessionId.generate()

    created_at = wf_dict.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)

    status_str = str(wf_dict.get("status", "pending")).lower()
    try:
        status = WorkflowStatus(status_str)
    except ValueError:
        status = WorkflowStatus.PENDING

    raw_steps = wf_dict.get("steps", [])
    domain_steps = [legacy_step_dict_to_domain(s) for s in raw_steps]

    return WorkflowRun(
        run_id=run_id,
        workflow_id=wf_id,
        session_id=session_id,
        created_at=created_at,
        status=status,
        steps=domain_steps,
    )


def domain_workflow_to_legacy_dict(wf_run: WorkflowRun) -> Dict[str, Any]:
    """Converts V2 WorkflowRun domain model to legacy dictionary format."""
    return {
        "workflow_id": str(wf_run.workflow_id),
        "run_id": str(wf_run.run_id),
        "session_id": str(wf_run.session_id),
        "created_at": wf_run.created_at.isoformat(),
        "status": wf_run.status.value,
        "steps": [domain_step_to_legacy_dict(s) for s in wf_run.steps],
    }
