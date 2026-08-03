"""
VideoProductionWorkflowPack — BaseWorkflowPack for the durable production workflow.

The pack builds the immutable DAG definition from the 16 canonical steps
(plan 05 §7) and is registered in the workflow registry like the other packs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition
from windagent_workflows.models import (
    ArtifactContract,
    CompletionPredicate,
    EdgeType,
    ImmutableWorkflowDefinition,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)
from windagent_workflows.video_production.definition import (
    STEP_OUTPUT_ARTIFACTS,
    VIDEO_PRODUCTION_STEPS,
    build_production_step_nodes,
)


class VideoProductionWorkflowPack(BaseWorkflowPack):
    """Durable video production workflow pack (plan 05 Phase 17)."""

    def __init__(self) -> None:
        definition = WorkflowPackDefinition(
            name="video_production",
            description=(
                "Durable end-to-end video production workflow: concept, screenplay, "
                "bibles, references, cinematic plan, shot plan, cost, render, review, "
                "post-production, verification and publish (plan 05 §7)."
            ),
            semantic_version="1.0.0",
            input_schema={
                "required": ["project_id", "revision_id", "revision_hash"],
            },
            acceptance_criteria=[
                "Workflow recovers from durable state",
                "Approvals point at the correct revision/hash",
                "Duplicate/stale writes cause no side effects",
                "Failure matrix never creates duplicate submits",
            ],
        )
        super().__init__(definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        """Legacy adapter — the pack primarily uses the DAG builder."""
        steps = []
        for idx, step_id in enumerate(VIDEO_PRODUCTION_STEPS, start=1):
            steps.append(
                WorkflowStep(
                    id=f"{step_id}_step",
                    name=step_id,
                    tool_name="production_step_executor",
                    order=idx,
                    parameters={
                        "step_id": step_id,
                        "project_id": params.get("project_id", ""),
                        "revision_id": params.get("revision_id", ""),
                    },
                )
            )
        return steps

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        """Build the immutable 16-step linear DAG with artifact contracts."""
        nodes: Dict[str, WorkflowNodeSpec] = {}
        edges: List[WorkflowEdgeSpec] = []

        step_nodes = build_production_step_nodes()
        for node in step_nodes:
            nodes[node.step_id] = WorkflowNodeSpec(
                id=node.step_id,
                name=node.step_id,
                tool_name="production_step_executor",
                max_attempts=node.max_attempts,
                output_artifacts=[
                    ArtifactContract(name=a)
                    for a in STEP_OUTPUT_ARTIFACTS.get(node.step_id, [])
                ],
                completion_predicate=CompletionPredicate(type="tool_success"),
            )

        previous: str | None = None
        for step_id in VIDEO_PRODUCTION_STEPS:
            if previous:
                edges.append(
                    WorkflowEdgeSpec(
                        from_node_id=previous,
                        to_node_id=step_id,
                        edge_type=EdgeType.DEPENDENCY,
                    )
                )
            previous = step_id

        definition = ImmutableWorkflowDefinition(
            id="video_production_1.0.0",
            name="video_production",
            semantic_version="1.0.0",
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=[
                ArtifactContract(name="project_record"),
                ArtifactContract(name="revision_record"),
            ],
            output_artifacts=[
                ArtifactContract(name="final_deliverable"),
                ArtifactContract(name="publication_record"),
            ],
        )
        definition.validate()
        return definition


__all__ = ["VideoProductionWorkflowPack"]
