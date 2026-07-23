"""
API V2 Workflows endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v2/workflows", tags=["Workflows V2"])


class WorkflowPackInfo(BaseModel):
    name: str
    description: str
    steps: List[str]
    acceptance_criteria: List[str]


class TriggerWorkflowRequest(BaseModel):
    workflow_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TriggerWorkflowResponse(BaseModel):
    run_id: str
    workflow_name: str
    status: str
    message: str


WORKFLOW_PACKS_CATALOG = [
    {
        "name": "bugfix",
        "description": "Automated bug reproduction, diagnosis, patching, and regression testing",
        "steps": ["reproduce", "diagnose", "patch", "focused_test", "regression", "review", "report"],
        "acceptance_criteria": ["Reproduction script passes", "Focused unit tests pass", "Zero regression"]
    },
    {
        "name": "ci_fix",
        "description": "CI pipeline log analysis and automated build repair",
        "steps": ["inspect_checks", "read_logs", "identify_root_cause", "patch", "rerun_focused_ci", "report"],
        "acceptance_criteria": ["CI build passes"]
    },
    {
        "name": "code_review",
        "description": "Pull request diff review, risk classification, and security check",
        "steps": ["diff_inventory", "risk_classification", "correctness", "security", "tests", "review_report"],
        "acceptance_criteria": ["Review report generated"]
    },
    {
        "name": "feature",
        "description": "Feature requirement analysis, design, implementation, and acceptance",
        "steps": ["requirements", "design", "implementation", "tests", "acceptance", "report"],
        "acceptance_criteria": ["All acceptance criteria met"]
    },
    {
        "name": "refactor",
        "description": "Incremental refactoring with behavioral baseline and parity testing",
        "steps": ["baseline_behavior", "dependency_map", "incremental_change", "parity_test", "regression"],
        "acceptance_criteria": ["Parity test passes"]
    },
    {
        "name": "research",
        "description": "Question decomposition, source quality check, synthesis, and citation",
        "steps": ["question_decomposition", "source_collection", "source_quality", "synthesis", "citation", "artifact"],
        "acceptance_criteria": ["Research report generated"]
    },
    {
        "name": "scientific_eval",
        "description": "Protocol freeze, data integrity check, benchmark execution, and verdict",
        "steps": ["protocol_freeze", "data_integrity", "leakage_checks", "execution", "metrics", "reproduction", "verdict"],
        "acceptance_criteria": ["Eval metrics computed"]
    },
    {
        "name": "release",
        "description": "Version bump, changelog, build, security scan, and rollback plan",
        "steps": ["version", "changelog", "build", "security_scan", "artifact_checksum", "smoke", "rollback_plan"],
        "acceptance_criteria": ["Artifact checksum verified", "Rollback plan confirmed"]
    }
]


@router.get("", response_model=List[WorkflowPackInfo])
async def list_workflows() -> List[WorkflowPackInfo]:
    return [WorkflowPackInfo(**w) for w in WORKFLOW_PACKS_CATALOG]


@router.post("/trigger", response_model=TriggerWorkflowResponse)
async def trigger_workflow(req: TriggerWorkflowRequest) -> TriggerWorkflowResponse:
    import uuid
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    return TriggerWorkflowResponse(
        run_id=run_id,
        workflow_name=req.workflow_name,
        status="TRIGGERED",
        message=f"Workflow pack '{req.workflow_name}' triggered successfully."
    )
