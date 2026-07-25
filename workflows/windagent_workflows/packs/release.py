"""
Release Workflow Pack for WindAgent Architecture V2 (Phase 23).
Flow: version -> changelog -> build -> [security_scan, artifact_checksum, smoke] (parallel) -> rollback_plan -> report.
Conditional edge: security scan failure blocks release.
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


class ReleaseWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="release",
            description="Manages production release packaging, security scanning, checksum generation, and rollback planning.",
            semantic_version="2.0.0",
            input_schema={"required": ["release_version"]},
            classification_rules=["release version", "prepare release", "publish release", "create release"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            required_tools=["exec_shell"],
            acceptance_criteria=[
                "Version & changelog updated",
                "Security scan passed",
                "Artifact checksum generated",
                "Smoke test passed",
                "Rollback plan documented",
                "No automatic production deployment without permission approval",
            ],
            input_artifacts=[
                ArtifactContract(name="release_version", description="Semantic version to release", required=True),
            ],
            output_artifacts=[
                ArtifactContract(name="release_artifacts", description="Release artifacts with checksums"),
                ArtifactContract(name="rollback_plan", description="Rollback plan documentation"),
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="version", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="changelog", tool_name="write_file"),
            WorkflowStep(id=StepId.generate(), order=3, name="build", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=4, name="security_scan", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=5, name="artifact_checksum", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=6, name="smoke", tool_name="exec_shell"),
            WorkflowStep(id=StepId.generate(), order=7, name="rollback_plan", tool_name="write_file"),
        ]

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        self.validate_input(params)

        nodes = {
            "step_1_version": WorkflowNodeSpec(
                id="step_1_version", name="version", tool_name="read_file",
                params={"description": "Bump version files"},
                output_artifacts=[ArtifactContract(name="version_files", description="Updated version files")],
            ),
            "step_2_changelog": WorkflowNodeSpec(
                id="step_2_changelog", name="changelog", tool_name="write_file",
                params={"description": "Update changelog with release notes"},
                output_artifacts=[ArtifactContract(name="changelog", description="Updated changelog")],
            ),
            "step_3_build": WorkflowNodeSpec(
                id="step_3_build", name="build", tool_name="exec_shell",
                params={"description": "Build release artifacts"},
                output_artifacts=[ArtifactContract(name="build_artifacts", description="Built artifacts")],
            ),
            "step_4_security": WorkflowNodeSpec(
                id="step_4_security", name="security_scan", tool_name="exec_shell",
                params={"description": "Run security vulnerability scan"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_5_checksum": WorkflowNodeSpec(
                id="step_5_checksum", name="artifact_checksum", tool_name="exec_shell",
                params={"description": "Generate artifact checksums"},
                output_artifacts=[ArtifactContract(name="checksums", description="Artifact checksums")],
            ),
            "step_6_smoke": WorkflowNodeSpec(
                id="step_6_smoke", name="smoke", tool_name="exec_shell",
                params={"description": "Run smoke test on built artifacts"},
                completion_predicate=CompletionPredicate(type="tool_success", expected_exit_code=0),
            ),
            "step_7_rollback": WorkflowNodeSpec(
                id="step_7_rollback", name="rollback_plan", tool_name="write_file",
                params={"description": "Document rollback plan"},
                output_artifacts=[ArtifactContract(name="rollback_plan", description="Rollback plan documentation")],
            ),
            "step_8_report": WorkflowNodeSpec(
                id="step_8_report", name="release_report", tool_name="write_file",
                params={"description": "Create release summary report"},
                output_artifacts=[ArtifactContract(name="release_report", description="Release summary")],
            ),
        }

        edges = [
            WorkflowEdgeSpec(from_node_id="step_1_version", to_node_id="step_2_changelog"),
            WorkflowEdgeSpec(from_node_id="step_2_changelog", to_node_id="step_3_build"),
            # Fan-out: build -> [security, checksum, smoke] (parallel)
            WorkflowEdgeSpec(from_node_id="step_3_build", to_node_id="step_4_security"),
            WorkflowEdgeSpec(from_node_id="step_3_build", to_node_id="step_5_checksum"),
            WorkflowEdgeSpec(from_node_id="step_3_build", to_node_id="step_6_smoke"),
            # Conditional: security pass -> rollback, fail -> report (blocked)
            WorkflowEdgeSpec(
                from_node_id="step_4_security", to_node_id="step_7_rollback",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
                label="Security scan passed",
            ),
            WorkflowEdgeSpec(
                from_node_id="step_4_security", to_node_id="step_8_report",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Security scan failed, skip to report",
            ),
            # Fan-in: [checksum, smoke] -> rollback
            WorkflowEdgeSpec(from_node_id="step_5_checksum", to_node_id="step_7_rollback"),
            WorkflowEdgeSpec(from_node_id="step_6_smoke", to_node_id="step_7_rollback"),
            # Conditional: smoke pass -> rollback (through checksum), fail -> report
            WorkflowEdgeSpec(
                from_node_id="step_6_smoke", to_node_id="step_8_report",
                edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code != 0",
                label="Smoke test failed, skip to report",
            ),
            WorkflowEdgeSpec(from_node_id="step_7_rollback", to_node_id="step_8_report"),
        ]

        definition = ImmutableWorkflowDefinition(
            id=f"release_{self.definition.semantic_version}",
            name="release",
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
