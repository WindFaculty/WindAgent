"""
CI Fix Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: inspect_checks -> read_logs -> identify_root_cause -> patch -> [rerun_ci, report] (parallel).
Conditional edges for retry on failure.
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


class CIFixWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="ci_fix",
            description="Fixes failing CI/CD build pipelines and test runners.",
            semantic_version="2.0.0",
            input_schema={"required": ["ci_log_url_or_content"]},
            classification_rules=["fix ci", "ci build failed", "pipeline error", "fix github action"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            required_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "CI log failure traceback analyzed",
                "Root cause identified",
                "Fix committed and verified on focused runner",
            ],
            input_artifacts=[
                ArtifactContract(name="ci_log", description="CI log content or URL", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="ci_fix_report", description="CI fix analysis and result report"),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="inspect_checks", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="read_logs", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="identify_root_cause", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="patch", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=5, name="rerun_focused_ci", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=6, name="report", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_inspect": WorkflowNodeSpec(
                id="step_1_inspect", name="inspect_checks", tool_name="read_file",
                params={"description": "Inspect CI check results"},
                output_artifacts=[ArtifactContract(name="ci_check_results", description="CI check output")],
            ),
            "step_2_read_logs": WorkflowNodeSpec(
                id="step_2_read_logs", name="read_logs", tool_name="read_file",
                params={"description": "Read CI failure logs"},
                output_artifacts=[ArtifactContract(name="ci_log_analysis", description="Parsed CI log")],
            ),
            "step_3_diagnose": WorkflowNodeSpec(
                id="step_3_diagnose", name="identify_root_cause", tool_name="read_file",
                params={"description": "Identify the root cause of CI failure"},
                output_artifacts=[ArtifactContract(name="root_cause_analysis", description="Root cause of CI failure")],
            ),
            "step_4_patch": WorkflowNodeSpec(
                id="step_4_patch", name="patch", tool_name="write_file",
                params={"description": "Apply CI fix"},
                output_artifacts=[ArtifactContract(name="ci_fix_patch", description="The applied CI fix")],
            ),
            "step_5_rerun_ci": WorkflowNodeSpec(
                id="step_5_rerun_ci", name="rerun_focused_ci", tool_name="exec_shell",
                params={"description": "Rerun focused CI pipeline"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_6_report": WorkflowNodeSpec(
                id="step_6_report", name="report", tool_name="write_file",
                params={"description": "Write CI fix report"},
                output_artifacts=[ArtifactContract(name="ci_fix_report", description="CI fix result report")],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_inspect", to_node_id="step_2_read_logs"),
            WorkflowEdgeSpec(from_node_id="step_2_read_logs", to_node_id="step_3_diagnose"),
            WorkflowEdgeSpec(from_node_id="step_3_diagnose", to_node_id="step_4_patch"),
            WorkflowEdgeSpec(from_node_id="step_4_patch", to_node_id="step_5_rerun_ci"),
            # Conditional: rerun pass -> report, fail -> patch (retry)
            WorkflowEdgeSpec(
                from_node_id="step_5_rerun_ci", to_node_id="step_6_report",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="CI passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_5_rerun_ci", to_node_id="step_4_patch",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="CI still failing, retry patch",
            ),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"ci_fix_{self.definition.semantic_version}",
            name="ci_fix",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
