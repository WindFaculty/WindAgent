"""
API V2 Workflow Runs endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/runs", tags=["Runs V2"])

IN_MEMORY_RUNS: Dict[str, Dict[str, Any]] = {
    "run_01": {
        "run_id": "run_01",
        "task_id": "task_demo",
        "workflow_name": "bugfix",
        "state": "COMPLETED",
        "current_step": "report",
        "step_count": 7,
        "duration_sec": 4.5
    }
}


class RunResponse(BaseModel):
    run_id: str
    task_id: str
    workflow_name: str
    state: str
    current_step: str
    step_count: int
    duration_sec: float


@router.get("", response_model=List[RunResponse])
async def list_runs() -> List[RunResponse]:
    return [RunResponse(**r) for r in IN_MEMORY_RUNS.values()]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    if run_id not in IN_MEMORY_RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return RunResponse(**IN_MEMORY_RUNS[run_id])
