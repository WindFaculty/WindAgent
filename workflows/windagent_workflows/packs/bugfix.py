"""
Bugfix Workflow Pack for WindAgent Architecture V2.
Flow: reproduce -> diagnose -> patch -> focused_test -> regression -> review -> report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class BugfixWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="bugfix",
            description="Diagnoses and fixes software bugs with reproduction and regression verification.",
            input_schema={"required": ["issue_description"]},
            classification_rules=["fix bug", "bugfix", "fix issue", "resolve error", "fix crash"],
            allowed_tools=["read_file", "write_file", "exec_shell", "code_search"],
            acceptance_criteria=[
                "Bug reproduced via test or log evidence",
                "Root cause identified and documented",
                "Focused test passes",
                "Zero regression in unit test suite",
            ],
            report_format="markdown",
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
