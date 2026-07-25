"""
Research Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: question_decomposition -> [source_collection, source_quality] (parallel) -> synthesis -> citation -> artifact.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition
from windagent_workflows.models import (
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate,
)


class ResearchWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="research",
            description="Decomposes research topics, gathers source materials, and synthesizes documented research artifacts.",
            semantic_version="2.0.0",
            input_schema={"required": ["research_topic"]},
            classification_rules=["research", "investigate", "study topic", "literature review"],
            allowed_tools=["open_url", "read_file", "write_file"],
            required_tools=["read_file", "write_file"],
            optional_tools=["open_url"],
            acceptance_criteria=[
                "Research questions decomposed",
                "Source quality & provenance verified",
                "Structured synthesis created with citations",
                "Persistent research markdown artifact written",
            ],
            input_artifacts=[
                ArtifactContract(name="research_topic", description="Research topic or question", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="research_artifact", description="Research artifact in markdown", required=True),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="question_decomposition", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="source_collection", tool_name="open_url"),
            WorkflowStep(id=StepId.generate(), order=3, name="source_quality", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="synthesis", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=5, name="citation", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=6, name="artifact", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_decomposition": WorkflowNodeSpec(
                id="step_1_decomposition", name="question_decomposition", tool_name="read_file",
                params={"description": "Decompose research questions"},
                output_artifacts=[ArtifactContract(name="research_questions", description="Decomposed research questions")],
            ),
            "step_2_collection": WorkflowNodeSpec(
                id="step_2_collection", name="source_collection", tool_name="open_url",
                params={"description": "Gather source materials"},
                output_artifacts=[ArtifactContract(name="source_materials", description="Collected source materials")],
            ),
            "step_3_quality": WorkflowNodeSpec(
                id="step_3_quality", name="source_quality", tool_name="read_file",
                params={"description": "Verify source quality and provenance"},
                output_artifacts=[ArtifactContract(name="source_quality_report", description="Source quality assessment")],
            ),
            "step_4_synthesis": WorkflowNodeSpec(
                id="step_4_synthesis", name="synthesis", tool_name="read_file",
                params={"description": "Synthesize research findings"},
                output_artifacts=[ArtifactContract(name="research_synthesis", description="Synthesized findings")],
            ),
            "step_5_citation": WorkflowNodeSpec(
                id="step_5_citation", name="citation", tool_name="read_file",
                params={"description": "Format citations and references"},
                output_artifacts=[ArtifactContract(name="citations", description="Formatted citations")],
            ),
            "step_6_artifact": WorkflowNodeSpec(
                id="step_6_artifact", name="artifact", tool_name="write_file",
                params={"description": "Write final research artifact"},
                output_artifacts=[ArtifactContract(name="research_artifact", description="Research artifact in markdown", required=True)],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_decomposition", to_node_id="step_2_collection"),
            # Parallel: collection -> [quality, synthesis]
            WorkflowEdgeSpec(from_node_id="step_2_collection", to_node_id="step_3_quality"),
            WorkflowEdgeSpec(from_node_id="step_2_collection", to_node_id="step_4_synthesis"),
            # Fan-in: [quality, synthesis] -> citation
            WorkflowEdgeSpec(from_node_id="step_3_quality", to_node_id="step_5_citation"),
            WorkflowEdgeSpec(from_node_id="step_4_synthesis", to_node_id="step_5_citation"),
            WorkflowEdgeSpec(from_node_id="step_5_citation", to_node_id="step_6_artifact"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"research_{self.definition.semantic_version}",
            name="research",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
