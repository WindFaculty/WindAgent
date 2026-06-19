"""Schemas for workflow and workflow steps.

Shape MUST match docs/event_protocol.md §6.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# Tool whitelist as defined in docs/event_protocol.md §6.
ToolName = Literal[
    "open_app",
    "open_url",
    "type_text",
    "hotkey",
    "press_key",
    "click_xy",
    "scroll",
    "screenshot",
    "wait",
]


WorkflowStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]
StepStatus = Literal["pending", "running", "success", "failed", "skipped", "cancelled"]


class WorkflowStep(BaseModel):
    id: UUID
    order: int = Field(..., ge=1)
    name: str
    tool_name: ToolName
    params: Dict[str, Any]
    status: StepStatus = "pending"


class Workflow(BaseModel):
    workflow_id: UUID
    session_id: UUID
    created_at: datetime
    status: WorkflowStatus = "pending"
    steps: List[WorkflowStep]