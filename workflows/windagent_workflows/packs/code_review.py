"""
Code Review Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: inventory -> [risk_classification, correctness, security] (parallel) -> tests -> review_report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition
from windagent_workflows.models import (
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, NodeType, EdgeType,
)


class CodeReviewWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="code_review",
            description="Performs automated code reviews, security vulnerability audits, and test coverage checks.",
            semantic_version="2.0.0",
            input_schema={"required": ["target_branch_or_diff"]},
            classification_rules=["code review", "review pr", "review diff", "audit code"],
            allowed_tools=["read_file", "exec_shell"],
            required_tools=["read_file", "exec_shell"],
            acceptance_criteria=[
                "Diff inventory analyzed",
                "Risk classification completed",
                "Correctness & security checks completed",
                "Zero automatic git merges without permission",
            ],
            input_artifacts=[
                ArtifactContract(name="target_diff", description="The diff or branch to review", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="review_report", description="Code review report", required=True),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="diff_inventory", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=2, name="risk_classification", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="correctness", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="security", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=5, name="tests", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=6, name="review_report", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_inventory": WorkflowNodeSpec(
                id="step_1_inventory", name="diff_inventory", tool_name="exec_shell",
                params={"description": "Inventory changed files"},
                output_artifacts=[ArtifactContract(name="changed_files", description="List of changed files")],
            ),
            "step_2_risk": WorkflowNodeSpec(
                id="step_2_risk", name="risk_classification", tool_name="read_file",
                params={"description": "Classify risk areas in the diff"},
                output_artifacts=[ArtifactContract(name="risk_analysis", description="Risk classification")],
            ),
            "step_3_correctness": WorkflowNodeSpec(
                id="step_3_correctness", name="correctness", tool_name="read_file",
                params={"description": "Check code correctness"},
                output_artifacts=[ArtifactContract(name="correctness_analysis", description="Correctness check results")],
            ),
            "step_4_security": WorkflowNodeSpec(
                id="step_4_security", name="security", tool_name="read_file",
                params={"description": "Security vulnerability review"},
                output_artifacts=[ArtifactContract(name="security_analysis", description="Security audit results")],
            ),
            "step_5_tests": WorkflowNodeSpec(
                id="step_5_tests", name="tests", tool_name="exec_shell",
                params={"description": "Run test suite against the changes"},
                completion_predicate=CompletionPredicate(type="tool_success"),
            ),
            "step_6_report": WorkflowNodeSpec(
                id="step_6_report", name="review_report", tool_name="write_file",
                params={"description": "Write comprehensive review report"},
                output_artifacts=[ArtifactContract(name="review_report", description="Code review report", required=True)],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_inventory", to_node_id="step_2_risk"),
            # Fan-out: risk -> [correctness, security] (parallel)
            WorkflowEdgeSpec(from_node_id="step_2_risk", to_node_id="step_3_correctness"),
            WorkflowEdgeSpec(from_node_id="step_2_risk", to_node_id="step_4_security"),
            # Fan-in: [correctness, security] -> tests
            WorkflowEdgeSpec(from_node_id="step_3_correctness", to_node_id="step_5_tests"),
            WorkflowEdgeSpec(from_node_id="step_4_security", to_node_id="step_5_tests"),
            WorkflowEdgeSpec(from_node_id="step_5_tests", to_node_id="step_6_report"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"code_review_{self.definition.semantic_version}",
            name="code_review",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
