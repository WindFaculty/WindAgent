"""
Feature Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: requirements -> design -> implementation -> [tests, docs] (parallel) -> review -> report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition
from windagent_workflows.models import (
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, EdgeType,
)


class FeatureWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="feature",
            description="Implements end-to-end features with requirement design and unit test verification.",
            semantic_version="2.0.0",
            input_schema={"required": ["feature_description"]},
            classification_rules=["add feature", "implement feature", "build feature", "new feature"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            required_tools=["write_file", "exec_shell"],
            acceptance_criteria=[
                "Requirements & architecture design documented",
                "Code implementation complete",
                "Unit and integration tests pass",
                "Acceptance criteria satisfied",
            ],
            input_artifacts=[
                ArtifactContract(name="feature_description", description="Description of the feature", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="implementation_code", description="Feature implementation code"),
                ArtifactContract(name="feature_report", description="Feature completion report"),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="requirements", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="design", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="implementation", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="tests", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=5, name="acceptance", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=6, name="report", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_requirements": WorkflowNodeSpec(
                id="step_1_requirements", name="requirements", tool_name="read_file",
                params={"description": "Analyze feature requirements"},
                output_artifacts=[ArtifactContract(name="requirements_doc", description="Feature requirements")],
            ),
            "step_2_design": WorkflowNodeSpec(
                id="step_2_design", name="design", tool_name="write_file",
                params={"description": "Design implementation architecture"},
                output_artifacts=[ArtifactContract(name="design_doc", description="Design document")],
            ),
            "step_3_implementation": WorkflowNodeSpec(
                id="step_3_implementation", name="implementation", tool_name="write_file",
                params={"description": "Write feature implementation code"},
                output_artifacts=[ArtifactContract(name="implementation_code", description="Implementation code")],
            ),
            "step_4_tests": WorkflowNodeSpec(
                id="step_4_tests", name="tests", tool_name="exec_shell",
                params={"description": "Write and run unit/integration tests"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_5_docs": WorkflowNodeSpec(
                id="step_5_docs", name="document", tool_name="write_file",
                params={"description": "Document the feature"},
                output_artifacts=[ArtifactContract(name="feature_docs", description="Feature documentation")],
            ),
            "step_6_review": WorkflowNodeSpec(
                id="step_6_review", name="review", tool_name="read_file",
                params={"description": "Final review of implementation"},
            ),
            "step_7_report": WorkflowNodeSpec(
                id="step_7_report", name="report", tool_name="write_file",
                params={"description": "Write feature completion report"},
                output_artifacts=[ArtifactContract(name="feature_report", description="Feature report")],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_requirements", to_node_id="step_2_design"),
            WorkflowEdgeSpec(from_node_id="step_2_design", to_node_id="step_3_implementation"),
            # Fan-out: implementation -> [tests, docs] (parallel)
            WorkflowEdgeSpec(from_node_id="step_3_implementation", to_node_id="step_4_tests"),
            WorkflowEdgeSpec(from_node_id="step_3_implementation", to_node_id="step_5_docs"),
            # Conditional: tests pass -> review, failure -> implementation (retry)
            WorkflowEdgeSpec(
                from_node_id="step_4_tests", to_node_id="step_6_review",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Tests passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_4_tests", to_node_id="step_3_implementation",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Tests failed, retry implementation",
            ),
            # Fan-in: [tests, docs] -> review
            WorkflowEdgeSpec(from_node_id="step_5_docs", to_node_id="step_6_review"),
            WorkflowEdgeSpec(from_node_id="step_6_review", to_node_id="step_7_report"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"feature_{self.definition.semantic_version}",
            name="feature",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
