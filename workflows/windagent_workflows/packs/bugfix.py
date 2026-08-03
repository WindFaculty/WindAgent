"""
Bugfix Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: reproduce -> diagnose -> patch -> [focused_test, regression] (parallel) -> review -> report.
Supports conditional edges for test results, artifact contracts, and completion predicates.
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


class BugfixWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="bugfix",
            description="Diagnoses and fixes software bugs with reproduction and regression verification.",
            semantic_version="2.0.0",
            input_schema={"required": ["issue_description"]},
            classification_rules=["fix bug", "bugfix", "fix issue", "resolve error", "fix crash"],
            allowed_tools=["read_file", "write_file", "exec_shell", "code_search"],
            required_tools=["exec_shell", "write_file"],
            optional_tools=["code_search"],
            acceptance_criteria=[
                "Bug reproduced via test or log evidence",
                "Root cause identified and documented",
                "Focused test passes",
                "Zero regression in unit test suite",
            ],
            report_format="markdown",
            input_artifacts=[
                ArtifactContract(name="issue_description", description="Description of the bug", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="fix_patch", description="The applied fix code", required=True),
                ArtifactContract(name="fix_report", description="Bugfix report in markdown", required=True),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="reproduce", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=2, name="diagnose", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="patch", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="focused_test", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=5, name="regression", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=6, name="review", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=7, name="report", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_reproduce": WorkflowNodeSpec(
                id="step_1_reproduce", name="reproduce", tool_name="exec_shell",
                params={"description": "Reproduce the bug with log evidence"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
                output_artifacts=[ArtifactContract(name="reproduction_evidence", description="Log output showing the bug")],
            ),
            "step_2_diagnose": WorkflowNodeSpec(
                id="step_2_diagnose", name="diagnose", tool_name="read_file",
                params={"description": "Identify root cause of the bug"},
                completion_predicate=CompletionPredicate(type="tool_success"),
                output_artifacts=[ArtifactContract(name="root_cause", description="Root cause analysis")],
            ),
            "step_3_patch": WorkflowNodeSpec(
                id="step_3_patch", name="patch", tool_name="write_file",
                params={"description": "Apply the fix"},
                completion_predicate=CompletionPredicate(type="tool_success"),
                output_artifacts=[ArtifactContract(name="fix_patch", description="The fix code", required=True)],
            ),
            "step_4_focused_test": WorkflowNodeSpec(
                id="step_4_focused_test", name="focused_test", tool_name="exec_shell",
                params={"description": "Run focused test for the fix"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_5_regression": WorkflowNodeSpec(
                id="step_5_regression", name="regression", tool_name="exec_shell",
                params={"description": "Run full regression suite"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_6_review": WorkflowNodeSpec(
                id="step_6_review", name="review", tool_name="read_file",
                params={"description": "Review the patch"},
                completion_predicate=CompletionPredicate(type="tool_success"),
            ),
            "step_7_report": WorkflowNodeSpec(
                id="step_7_report", name="report", tool_name="write_file",
                params={"description": "Write bugfix report"},
                completion_predicate=CompletionPredicate(type="tool_success"),
                output_artifacts=[ArtifactContract(name="fix_report", description="Bugfix report")],
            ),
        }

        edges = [
            # Sequential: reproduce -> diagnose -> patch
            WorkflowEdgeSpec(from_node_id="step_1_reproduce", to_node_id="step_2_diagnose"),
            WorkflowEdgeSpec(from_node_id="step_2_diagnose", to_node_id="step_3_patch"),
            # Fan-out: patch -> [focused_test, regression] (parallel)
            WorkflowEdgeSpec(from_node_id="step_3_patch", to_node_id="step_4_focused_test"),
            WorkflowEdgeSpec(from_node_id="step_3_patch", to_node_id="step_5_regression"),
            # Conditional: focused_test success -> review, failure -> patch (retry)
            WorkflowEdgeSpec(
                from_node_id="step_4_focused_test", to_node_id="step_6_review",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Tests passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_4_focused_test", to_node_id="step_3_patch",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Tests failed, retry patch",
            ),
            # regression -> review (fan-in)
            WorkflowEdgeSpec(from_node_id="step_5_regression", to_node_id="step_6_review"),
            # review -> report
            WorkflowEdgeSpec(from_node_id="step_6_review", to_node_id="step_7_report"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"bugfix_{self.definition.semantic_version}",
            name="bugfix",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
