"""
Scientific Evaluation Workflow Pack for WindAgent Architecture V2.
Flow: protocol_freeze -> data_integrity -> leakage_checks -> execution -> metrics -> reproduction -> verdict.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class ScientificEvalWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="scientific_eval",
            description="Executes benchmark protocols with data integrity and holdout leakage protection.",
            input_schema={"required": ["eval_protocol_id"]},
            classification_rules=["scientific eval", "run benchmark", "eval suite", "evaluate model"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "Protocol frozen and hashed",
                "Holdout data non-contamination verified",
                "Metrics and reproduction logs recorded",
                "Final evaluation verdict produced",
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
