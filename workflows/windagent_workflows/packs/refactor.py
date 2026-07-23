"""
Refactor Workflow Pack for WindAgent Architecture V2.
Flow: baseline_behavior -> dependency_map -> incremental_change -> parity_test -> regression.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class RefactorWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="refactor",
            description="Refactors legacy code to V2 architecture while ensuring strict parity and zero regression.",
            input_schema={"required": ["target_module"]},
            classification_rules=["refactor", "clean up code", "restructure module", "decouple code"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "Baseline test suite recorded",
                "Incremental change applied",
                "Parity tests pass with zero behavior change",
                "Regression test suite passes",
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
