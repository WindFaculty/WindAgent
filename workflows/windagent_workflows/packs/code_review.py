"""
Code Review Workflow Pack for WindAgent Architecture V2.
Flow: diff_inventory -> risk_classification -> correctness -> security -> tests -> review_report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class CodeReviewWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="code_review",
            description="Performs automated code reviews, security vulnerability audits, and test coverage checks.",
            input_schema={"required": ["target_branch_or_diff"]},
            classification_rules=["code review", "review pr", "review diff", "audit code"],
            allowed_tools=["read_file", "exec_shell"],
            acceptance_criteria=[
                "Diff inventory analyzed",
                "Risk classification completed",
                "Correctness & security checks completed",
                "Zero automatic git merges without permission",
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
