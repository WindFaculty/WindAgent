"""
Code Video Workflow Definition — 9 durable pipeline steps.

The step sequence for deterministic code tutorial video production:

    COMPILE_PLAN
    → BUILD_WORKSPACE
    → VERIFY_TUTORIAL
    → RENDER_STUDIO
    → RUN_REPLAY
    → CAPTURE_TAKES
    → RENDER_GRAPHICS
    → ASSEMBLE_MASTER
    → FINAL_QC

Each step defines: step id/version, input revision/hash semantics,
preconditions, operation, expected events, checkpoint policy, retry class /
budget, output artifact types, and scheduler-ready node generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_orchestration.production.approvals import ProductionApprovalGate
from windagent_orchestration.production.scheduler import ProductionStepNode

CODE_VIDEO_STEPS: List[str] = [
    "COMPILE_PLAN",
    "BUILD_WORKSPACE",
    "VERIFY_TUTORIAL",
    "RENDER_STUDIO",
    "RUN_REPLAY",
    "CAPTURE_TAKES",
    "RENDER_GRAPHICS",
    "ASSEMBLE_MASTER",
    "FINAL_QC",
]

# step_id -> approval gate required before the step may start
STEP_APPROVAL_GATES: Dict[str, ProductionApprovalGate] = {
    "VERIFY_TUTORIAL": ProductionApprovalGate.CODE_REVIEW_APPROVAL
    if hasattr(ProductionApprovalGate, "CODE_REVIEW_APPROVAL")
    else ProductionApprovalGate.CONCEPT_APPROVAL,
    "FINAL_QC": ProductionApprovalGate.FINAL_CUT_APPROVAL,
}

# step_id -> step version
STEP_VERSIONS: Dict[str, int] = {step: 1 for step in CODE_VIDEO_STEPS}

# step_id -> retry class/budget
STEP_RETRY_CLASS: Dict[str, str] = {
    "COMPILE_PLAN": "fast",
    "BUILD_WORKSPACE": "fast",
    "VERIFY_TUTORIAL": "fast",
    "RENDER_STUDIO": "render",
    "RUN_REPLAY": "fast",
    "CAPTURE_TAKES": "render",
    "RENDER_GRAPHICS": "render",
    "ASSEMBLE_MASTER": "render",
    "FINAL_QC": "review",
}

# step_id -> whether external provider credits are consumed (all False for deterministic offline video 02)
STEP_EXTERNAL_COST: Dict[str, bool] = {step: False for step in CODE_VIDEO_STEPS}

# step_id -> output artifact types
STEP_OUTPUT_ARTIFACTS: Dict[str, List[str]] = {
    "COMPILE_PLAN": ["video_plan", "cue_sheet"],
    "BUILD_WORKSPACE": ["tutorial_workspace", "workspace_manifest"],
    "VERIFY_TUTORIAL": ["test_receipt", "checkpoint_receipts"],
    "RENDER_STUDIO": ["studio_layout", "theme_config"],
    "RUN_REPLAY": ["action_trace", "terminal_receipts"],
    "CAPTURE_TAKES": ["take_receipts", "raw_clips"],
    "RENDER_GRAPHICS": ["diagram_assets", "title_cards"],
    "ASSEMBLE_MASTER": ["assembled_master_1440p", "assembled_master_1080p", "timeline_manifest"],
    "FINAL_QC": ["qc_report", "final_verdict"],
}

# step_id -> expected events
STEP_EXPECTED_EVENTS: Dict[str, List[str]] = {
    "COMPILE_PLAN": ["code_video.plan_compiled"],
    "BUILD_WORKSPACE": ["code_video.workspace_ready"],
    "VERIFY_TUTORIAL": ["code_video.tutorial_verified"],
    "RENDER_STUDIO": ["code_video.studio_ready"],
    "RUN_REPLAY": ["code_video.replay_completed"],
    "CAPTURE_TAKES": ["code_video.takes_captured"],
    "RENDER_GRAPHICS": ["code_video.graphics_rendered"],
    "ASSEMBLE_MASTER": ["code_video.master_assembled"],
    "FINAL_QC": ["code_video.qc_verified"],
}

# step_id -> max retry attempts
STEP_MAX_ATTEMPTS: Dict[str, int] = {
    "COMPILE_PLAN": 2,
    "BUILD_WORKSPACE": 3,
    "VERIFY_TUTORIAL": 2,
    "RENDER_STUDIO": 3,
    "RUN_REPLAY": 2,
    "CAPTURE_TAKES": 3,
    "RENDER_GRAPHICS": 3,
    "ASSEMBLE_MASTER": 3,
    "FINAL_QC": 2,
}


def build_code_video_step_nodes() -> List[ProductionStepNode]:
    """Build the scheduler-ready step graph (linear DAG with approval gates)."""
    nodes: List[ProductionStepNode] = []
    for idx, step in enumerate(CODE_VIDEO_STEPS):
        deps = (CODE_VIDEO_STEPS[idx - 1],) if idx > 0 else ()
        nodes.append(
            ProductionStepNode(
                step_id=step,
                dependencies=deps,
                approval_gate=STEP_APPROVAL_GATES.get(step),
                external_cost=STEP_EXTERNAL_COST[step],
                max_attempts=STEP_MAX_ATTEMPTS[step],
            )
        )
    return nodes


def step_contract(step_id: str) -> Dict[str, Any]:
    """Return the full step contract for one code video step id."""
    if step_id not in CODE_VIDEO_STEPS:
        raise KeyError(f"Unknown code video step '{step_id}'")
    return {
        "step_id": step_id,
        "version": STEP_VERSIONS[step_id],
        "input_revision_hash": "script.sha256",
        "preconditions": "all dependency steps completed; approval gate satisfied if any",
        "operation": f"code_video.step_executor.{step_id.lower()}",
        "expected_events": STEP_EXPECTED_EVENTS[step_id],
        "checkpoint": "current_step + attempt + input/output hashes",
        "retry_class": STEP_RETRY_CLASS[step_id],
        "retry_budget": STEP_MAX_ATTEMPTS[step_id],
        "approval_requirement": (
            STEP_APPROVAL_GATES[step_id].value if step_id in STEP_APPROVAL_GATES else "none"
        ),
        "output_artifact_types": STEP_OUTPUT_ARTIFACTS[step_id],
        "external_cost": STEP_EXTERNAL_COST[step_id],
    }


def all_step_contracts() -> List[Dict[str, Any]]:
    return [step_contract(step) for step in CODE_VIDEO_STEPS]


__all__ = [
    "CODE_VIDEO_STEPS",
    "STEP_APPROVAL_GATES",
    "STEP_VERSIONS",
    "STEP_RETRY_CLASS",
    "STEP_EXTERNAL_COST",
    "STEP_OUTPUT_ARTIFACTS",
    "STEP_EXPECTED_EVENTS",
    "STEP_MAX_ATTEMPTS",
    "build_code_video_step_nodes",
    "step_contract",
    "all_step_contracts",
]
