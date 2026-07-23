"""
Research Workflow Pack for WindAgent Architecture V2.
Flow: question_decomposition -> source_collection -> source_quality -> synthesis -> citation -> artifact.
"""

from __future__ import annotations
from typing import Any, Dict, List

from windagent_core.domain.types import StepId
from windagent_core.domain.models import WorkflowStep
from windagent_workflows.base import BaseWorkflowPack, WorkflowPackDefinition


class ResearchWorkflowPack(BaseWorkflowPack):
    def __init__(self):
        definition = WorkflowPackDefinition(
            name="research",
            description="Decomposes research topics, gathers source materials, and synthesizes documented research artifacts.",
            input_schema={"required": ["research_topic"]},
            classification_rules=["research", "investigate", "study topic", "literature review"],
            allowed_tools=["open_url", "read_file", "write_file"],
            acceptance_criteria=[
                "Research questions decomposed",
                "Source quality & provenance verified",
                "Structured synthesis created with citations",
                "Persistent research markdown artifact written",
            ],
        )
        super().__init__(definition=definition)

    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        self.validate_input(params)
        return [
            WorkflowStep(id=StepId.generate(), order=1, name="question_decomposition", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=2, name="source_collection", tool_name="open_url"),
            WorkflowStep(id=StepId.generate(), order=3, name="source_quality", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=4, name="synthesis", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=5, name="citation", tool_name="read_file"),
            WorkflowStep(id=StepId.generate(), order=6, name="artifact", tool_name="write_file"),
        ]
