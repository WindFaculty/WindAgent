"""
Video production workflow definition — 16 durable steps (plan 05 §7).

The step sequence:

    CREATE_PROJECT
    → GENERATE_CONCEPTS
    → SELECT_CONCEPT
    → GENERATE_SCREENPLAY
    → LOCK_SCREENPLAY
    → BUILD_CHARACTER_AND_LOCATION_BIBLES
    → APPROVE_REFERENCES
    → CREATE_CINEMATIC_PLAN
    → LOCK_SHOT_PLAN
    → ESTIMATE_COST
    → RENDER_ASSETS
    → RENDER_SHOTS
    → REVIEW_CANDIDATES
    → POST_PRODUCTION
    → FINAL_VERIFICATION
    → PUBLISH

Each step defines: step id/version, input revision/hash semantics,
preconditions, operation, expected events, checkpoint policy, retry class /
budget, compensation or recovery, approval requirement and output artifact
types. This module builds the scheduler-ready `ProductionStepNode` list.
"""

from __future__ import annotations

from typing import Any, Dict, List

from windagent_orchestration.production.approvals import ProductionApprovalGate
from windagent_orchestration.production.scheduler import ProductionStepNode

VIDEO_PRODUCTION_STEPS: List[str] = [
    "CREATE_PROJECT",
    "GENERATE_CONCEPTS",
    "SELECT_CONCEPT",
    "GENERATE_SCREENPLAY",
    "LOCK_SCREENPLAY",
    "BUILD_CHARACTER_AND_LOCATION_BIBLES",
    "APPROVE_REFERENCES",
    "CREATE_CINEMATIC_PLAN",
    "LOCK_SHOT_PLAN",
    "ESTIMATE_COST",
    "RENDER_ASSETS",
    "RENDER_SHOTS",
    "REVIEW_CANDIDATES",
    "POST_PRODUCTION",
    "FINAL_VERIFICATION",
    "PUBLISH",
]

# step_id -> approval gate required before the step may start (plan 05 §8.2)
STEP_APPROVAL_GATES: Dict[str, ProductionApprovalGate] = {
    "SELECT_CONCEPT": ProductionApprovalGate.CONCEPT_APPROVAL,
    "LOCK_SCREENPLAY": ProductionApprovalGate.SCREENPLAY_APPROVAL,
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": ProductionApprovalGate.CHARACTER_APPROVAL,
    "APPROVE_REFERENCES": ProductionApprovalGate.LOCATION_APPROVAL,
    "LOCK_SHOT_PLAN": ProductionApprovalGate.SHOT_PLAN_APPROVAL,
    "ESTIMATE_COST": ProductionApprovalGate.COST_APPROVAL,
    "PUBLISH": ProductionApprovalGate.FINAL_CUT_APPROVAL,
}

# step_id -> step version (bump on contract change → new workflow definition)
STEP_VERSIONS: Dict[str, int] = {step: 1 for step in VIDEO_PRODUCTION_STEPS}

# step_id -> retry class/budget + whether it consumes external (provider) credits
STEP_RETRY_CLASS: Dict[str, str] = {
    "CREATE_PROJECT": "fast",
    "GENERATE_CONCEPTS": "llm",
    "SELECT_CONCEPT": "fast",
    "GENERATE_SCREENPLAY": "llm",
    "LOCK_SCREENPLAY": "fast",
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": "llm",
    "APPROVE_REFERENCES": "fast",
    "CREATE_CINEMATIC_PLAN": "llm",
    "LOCK_SHOT_PLAN": "fast",
    "ESTIMATE_COST": "fast",
    "RENDER_ASSETS": "provider",
    "RENDER_SHOTS": "provider",
    "REVIEW_CANDIDATES": "review",
    "POST_PRODUCTION": "render",
    "FINAL_VERIFICATION": "review",
    "PUBLISH": "fast",
}

# step_id -> provider/credit consuming (Release 0.1: concurrency 1)
STEP_EXTERNAL_COST: Dict[str, bool] = {
    "CREATE_PROJECT": False,
    "GENERATE_CONCEPTS": False,
    "SELECT_CONCEPT": False,
    "GENERATE_SCREENPLAY": False,
    "LOCK_SCREENPLAY": False,
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": False,
    "APPROVE_REFERENCES": False,
    "CREATE_CINEMATIC_PLAN": False,
    "LOCK_SHOT_PLAN": False,
    "ESTIMATE_COST": False,
    "RENDER_ASSETS": True,
    "RENDER_SHOTS": True,
    "REVIEW_CANDIDATES": False,
    "POST_PRODUCTION": False,
    "FINAL_VERIFICATION": False,
    "PUBLISH": False,
}

# step_id -> output artifact types (plan 05 §7 "output artifact types")
STEP_OUTPUT_ARTIFACTS: Dict[str, List[str]] = {
    "CREATE_PROJECT": ["project_record", "revision_record"],
    "GENERATE_CONCEPTS": ["concept_set"],
    "SELECT_CONCEPT": ["selected_concept"],
    "GENERATE_SCREENPLAY": ["screenplay"],
    "LOCK_SCREENPLAY": ["locked_screenplay", "screenplay_hash"],
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": ["character_bible", "location_bible", "prop_bible", "style_bible"],
    "APPROVE_REFERENCES": ["approved_reference_bindings"],
    "CREATE_CINEMATIC_PLAN": ["cinematic_plan"],
    "LOCK_SHOT_PLAN": ["locked_shot_plan", "shot_graph_hash"],
    "ESTIMATE_COST": ["cost_estimate"],
    "RENDER_ASSETS": ["reference_assets", "asset_hashes"],
    "RENDER_SHOTS": ["shot_clips", "candidate_set"],
    "REVIEW_CANDIDATES": ["reviewed_candidates", "review_report"],
    "POST_PRODUCTION": ["edited_sequence", "dialogue_track", "bgm_mix"],
    "FINAL_VERIFICATION": ["verification_report"],
    "PUBLISH": ["final_deliverable", "publication_record"],
}

# step_id -> expected events (plan 05 §7 "expected events")
STEP_EXPECTED_EVENTS: Dict[str, List[str]] = {
    "CREATE_PROJECT": ["video_production.project_created"],
    "GENERATE_CONCEPTS": ["video_production.concepts_generated"],
    "SELECT_CONCEPT": ["video_production.concept_approved"],
    "GENERATE_SCREENPLAY": ["video_production.screenplay_generated"],
    "LOCK_SCREENPLAY": ["video_production.screenplay_locked"],
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": [
        "video_production.character_bible_approved",
        "video_production.location_bible_approved",
    ],
    "APPROVE_REFERENCES": ["video_production.references_approved"],
    "CREATE_CINEMATIC_PLAN": ["video_production.cinematic_plan_generated"],
    "LOCK_SHOT_PLAN": ["video_production.shot_plan_locked"],
    "ESTIMATE_COST": ["video_production.cost_estimated"],
    "RENDER_ASSETS": ["video_production.assets_rendered"],
    "RENDER_SHOTS": ["video_production.generation_submitted", "video_production.generation_completed"],
    "REVIEW_CANDIDATES": ["video_production.generation_rejected", "video_production.sequence_completed"],
    "POST_PRODUCTION": ["video_production.post_production_completed"],
    "FINAL_VERIFICATION": ["video_production.final_verification_completed"],
    "PUBLISH": ["video_production.final_video_published"],
}

# step_id -> max attempts (retry budget, plan 05 §7 "retry class/budget")
STEP_MAX_ATTEMPTS: Dict[str, int] = {
    "CREATE_PROJECT": 2,
    "GENERATE_CONCEPTS": 3,
    "SELECT_CONCEPT": 2,
    "GENERATE_SCREENPLAY": 3,
    "LOCK_SCREENPLAY": 2,
    "BUILD_CHARACTER_AND_LOCATION_BIBLES": 3,
    "APPROVE_REFERENCES": 2,
    "CREATE_CINEMATIC_PLAN": 3,
    "LOCK_SHOT_PLAN": 2,
    "ESTIMATE_COST": 2,
    "RENDER_ASSETS": 3,
    "RENDER_SHOTS": 3,
    "REVIEW_CANDIDATES": 2,
    "POST_PRODUCTION": 3,
    "FINAL_VERIFICATION": 2,
    "PUBLISH": 2,
}


def build_production_step_nodes() -> List[ProductionStepNode]:
    """Build the scheduler-ready step graph (linear DAG with approval gates)."""
    nodes: List[ProductionStepNode] = []
    for idx, step in enumerate(VIDEO_PRODUCTION_STEPS):
        deps = (VIDEO_PRODUCTION_STEPS[idx - 1],) if idx > 0 else ()
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
    """Return the full step contract (plan 05 §7) for one step id."""
    if step_id not in VIDEO_PRODUCTION_STEPS:
        raise KeyError(f"Unknown production step {step_id}")
    return {
        "step_id": step_id,
        "version": STEP_VERSIONS[step_id],
        "input_revision_hash": "revision.content_hash",
        "preconditions": "all dependency steps completed; approval gate satisfied if any",
        "operation": "step_executor.execute",
        "expected_events": STEP_EXPECTED_EVENTS[step_id],
        "checkpoint": "current_step + attempt + input/output hashes + lease + pending external op",
        "retry_class": STEP_RETRY_CLASS[step_id],
        "retry_budget": STEP_MAX_ATTEMPTS[step_id],
        "compensation_or_recovery": "inspect durable state + provider before retry; never blind resubmit",
        "approval_requirement": (
            STEP_APPROVAL_GATES[step_id].value if step_id in STEP_APPROVAL_GATES else "none"
        ),
        "output_artifact_types": STEP_OUTPUT_ARTIFACTS[step_id],
        "external_cost": STEP_EXTERNAL_COST[step_id],
    }


def all_step_contracts() -> List[Dict[str, Any]]:
    return [step_contract(step) for step in VIDEO_PRODUCTION_STEPS]


__all__ = [
    "VIDEO_PRODUCTION_STEPS",
    "STEP_APPROVAL_GATES",
    "STEP_VERSIONS",
    "STEP_RETRY_CLASS",
    "STEP_EXTERNAL_COST",
    "STEP_OUTPUT_ARTIFACTS",
    "STEP_EXPECTED_EVENTS",
    "STEP_MAX_ATTEMPTS",
    "build_production_step_nodes",
    "step_contract",
    "all_step_contracts",
]
