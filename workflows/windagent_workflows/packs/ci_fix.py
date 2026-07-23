"""
CI Fix Workflow Pack for WindAgent Architecture V2.
Flow: inspect_checks -> read_logs -> identify_root_cause -> patch -> rerun_focused_ci -> report.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class CIFixWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="ci_fix",
            description="Fixes failing CI/CD build pipelines and test runners.",
            input_schema={"required": ["ci_log_url_or_content"]},
            classification_rules=["fix ci", "ci build failed", "pipeline error", "fix github action"],
            allowed_tools=["read_file", "write_file", "exec_shell"],
            acceptance_criteria=[
                "CI log failure traceback analyzed",
                "Root cause identified",
                "Fix committed and verified on focused runner",
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
