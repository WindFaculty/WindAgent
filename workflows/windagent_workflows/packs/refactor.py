"""
Refactor Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: baseline -> dependency_map -> incremental_change -> [parity_test, regression] (parallel).
Conditional loop on parity test failure.
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


class RefactorWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="refactor",
            description="Refactors legacy code to V2 architecture while ensuring strict parity and zero regression.",
            semantic_version="2.0.0",
            input_schema={"required": ["target_module"]},
            classification_rules=["refactor", "clean up code", "restructure module", "decouple code"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            required_tools=["read_file", "write_file"],
            acceptance_criteria=[
                "Baseline test suite recorded",
                "Incremental change applied",
                "Parity tests pass with zero behavior change",
                "Regression test suite passes",
            ],
            input_artifacts=[
                ArtifactContract(name="target_module", description="Module path to refactor", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="refactored_code", description="The refactored code"),
                ArtifactContract(name="refactor_report", description="Refactoring summary report"),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="baseline_behavior", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=2, name="dependency_map", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="incremental_change", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="parity_test", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=5, name="regression", tool_name="exec_shell"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_baseline": WorkflowNodeSpec(
                id="step_1_baseline", name="baseline_behavior", tool_name="exec_shell",
                params={"description": "Record baseline test suite behavior"},
                output_artifacts=[ArtifactContract(name="baseline_tests", description="Baseline test output")],
            ),
            "step_2_deps": WorkflowNodeSpec(
                id="step_2_deps", name="dependency_map", tool_name="read_file",
                params={"description": "Analyze module dependency map"},
                output_artifacts=[ArtifactContract(name="dependency_map", description="Module dependency analysis")],
            ),
            "step_3_change": WorkflowNodeSpec(
                id="step_3_change", name="incremental_change", tool_name="write_file",
                params={"description": "Apply incremental refactoring change"},
                output_artifacts=[ArtifactContract(name="refactored_code", description="The refactored code")],
            ),
            "step_4_parity": WorkflowNodeSpec(
                id="step_4_parity", name="parity_test", tool_name="exec_shell",
                params={"description": "Run parity tests to verify zero behavior change"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_5_regression": WorkflowNodeSpec(
                id="step_5_regression", name="regression", tool_name="exec_shell",
                params={"description": "Run full regression suite"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_6_report": WorkflowNodeSpec(
                id="step_6_report", name="report", tool_name="write_file",
                params={"description": "Write refactoring report"},
                output_artifacts=[ArtifactContract(name="refactor_report", description="Refactoring summary report")],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_baseline", to_node_id="step_2_deps"),
            WorkflowEdgeSpec(from_node_id="step_2_deps", to_node_id="step_3_change"),
            WorkflowEdgeSpec(from_node_id="step_3_change", to_node_id="step_4_parity"),
            # Conditional: parity pass -> regression, fail -> change (retry)
            WorkflowEdgeSpec(
                from_node_id="step_4_parity", to_node_id="step_5_regression",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Parity test passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_4_parity", to_node_id="step_3_change",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Parity test failed, retry change",
            ),
            WorkflowEdgeSpec(from_node_id="step_5_regression", to_node_id="step_6_report"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"refactor_{self.definition.semantic_version}",
            name="refactor",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
