"""
Scientific Evaluation Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: protocol_freeze -> [data_integrity, leakage_checks] (parallel) -> [execution, metrics, reproduction] -> verdict.
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


class ScientificEvalWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="scientific_eval",
            description="Executes benchmark protocols with data integrity and holdout leakage protection.",
            semantic_version="2.0.0",
            input_schema={"required": ["eval_protocol_id"]},
            classification_rules=["scientific eval", "run benchmark", "eval suite", "evaluate model"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            required_tools=["exec_shell"],
            acceptance_criteria=[
                "Protocol frozen and hashed",
                "Holdout data non-contamination verified",
                "Metrics and reproduction logs recorded",
                "Final evaluation verdict produced",
            ],
            input_artifacts=[
                ArtifactContract(name="eval_protocol", description="Evaluation protocol ID", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="eval_verdict", description="Final evaluation verdict", required=True),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="protocol_freeze", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="data_integrity", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=3, name="leakage_checks", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=4, name="execution", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=5, name="metrics", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=6, name="reproduction", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=7, name="verdict", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_freeze": WorkflowNodeSpec(
                id="step_1_freeze", name="protocol_freeze", tool_name="read_file",
                params={"description": "Freeze and hash the evaluation protocol"},
                output_artifacts=[ArtifactContract(name="protocol_hash", description="Frozen protocol hash")],
            ),
            "step_2_integrity": WorkflowNodeSpec(
                id="step_2_integrity", name="data_integrity", tool_name="exec_shell",
                params={"description": "Verify data integrity"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_3_leakage": WorkflowNodeSpec(
                id="step_3_leakage", name="leakage_checks", tool_name="exec_shell",
                params={"description": "Check for holdout data leakage"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_4_execution": WorkflowNodeSpec(
                id="step_4_execution", name="execution", tool_name="exec_shell",
                params={"description": "Run the evaluation benchmarks"},
                output_artifacts=[ArtifactContract(name="eval_results", description="Raw evaluation results")],
            ),
            "step_5_metrics": WorkflowNodeSpec(
                id="step_5_metrics", name="metrics", tool_name="read_file",
                params={"description": "Compute evaluation metrics from results"},
                output_artifacts=[ArtifactContract(name="eval_metrics", description="Computed evaluation metrics")],
            ),
            "step_6_reproduction": WorkflowNodeSpec(
                id="step_6_reproduction", name="reproduction", tool_name="exec_shell",
                params={"description": "Run reproduction verification"},
                output_artifacts=[ArtifactContract(name="reproduction_log", description="Reproduction verification log")],
            ),
            "step_7_verdict": WorkflowNodeSpec(
                id="step_7_verdict", name="verdict", tool_name="write_file",
                params={"description": "Produce final evaluation verdict"},
                output_artifacts=[ArtifactContract(name="eval_verdict", description="Final evaluation verdict", required=True)],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_freeze", to_node_id="step_2_integrity"),
            # Conditional gates: integrity/leakage failure blocks execution
            WorkflowEdgeSpec(
                from_node_id="step_2_integrity", to_node_id="step_3_leakage",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Data integrity check passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_2_integrity", to_node_id="step_7_verdict",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Data integrity check failed, skip to verdict",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_3_leakage", to_node_id="step_4_execution",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Leakage check passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_3_leakage", to_node_id="step_7_verdict",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Leakage check failed, skip to verdict",
            ),
            # Fan-out: execution -> [metrics, reproduction] (parallel)
            WorkflowEdgeSpec(from_node_id="step_4_execution", to_node_id="step_5_metrics"),
            WorkflowEdgeSpec(from_node_id="step_4_execution", to_node_id="step_6_reproduction"),
            # Fan-in: [metrics, reproduction] -> verdict
            WorkflowEdgeSpec(from_node_id="step_5_metrics", to_node_id="step_7_verdict"),
            WorkflowEdgeSpec(from_node_id="step_6_reproduction", to_node_id="step_7_verdict"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"scientific_eval_{self.definition.semantic_version}",
            name="scientific_eval",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
