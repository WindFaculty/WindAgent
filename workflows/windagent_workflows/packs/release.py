"""
Release Workflow Pack for WindAgent Architecture V2.
Flow: version -> changelog -> build -> security_scan -> artifact_checksum -> smoke -> rollback_plan.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class ReleaseWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="release",
            description="Manages production release packaging, security scanning, checksum generation, and rollback planning.",
            input_schema={"required": ["release_version"]},
            classification_rules=["release version", "prepare release", "publish release", "create release"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "Version & changelog updated",
                "Security scan passed",
                "Artifact checksum generated",
                "Smoke test passed",
                "Rollback plan documented",
                "No automatic production deployment without permission approval",
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
