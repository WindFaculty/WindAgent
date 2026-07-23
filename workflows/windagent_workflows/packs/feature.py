"""
Feature Workflow Pack for WindAgent Architecture V2.
Flow: requirements -> design -> implementation -> tests -> acceptance -> report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class FeatureWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="feature",
            description="Implements end-to-end features with requirement design and unit test verification.",
            input_schema={"required": ["feature_description"]},
            classification_rules=["add feature", "implement feature", "build feature", "new feature"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "Requirements & architecture design documented",
                "Code implementation complete",
                "Unit and integration tests pass",
                "Acceptance criteria satisfied",
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
