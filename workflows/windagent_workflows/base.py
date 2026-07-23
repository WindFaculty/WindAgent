"""
Workflow Pack Contract & Base Implementation for WindAgent Architecture V2.
Declares WorkflowPackDefinition and BaseWorkflowPack interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.domain.models import WorkflowStep
from windagent_core.errors.exceptions import ValidationError


@dataclass
class WorkflowPackDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    classification_rules: List[str] = field(default_factory=list)
    planning_policy: Dict[str, Any] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    model_requirements: Dict[str, Any] = field(default_factory=dict)
    permission_policy: Dict[str, Any] = field(default_factory=dict)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    verification_policy: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: List[str] = field(default_factory=list)
    report_format: str = "markdown"

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationError("Workflow pack name cannot be empty.")
        if not self.acceptance_criteria:
            raise ValidationError(f"Workflow pack [{self.name}] must declare acceptance criteria.")


class BaseWorkflowPack(ABC):
    def __init__(self, definition: WorkflowPackDefinition):
        definition.validate()
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    def validate_input(self, params: Dict[str, Any]) -> None:
        """Validates input parameters against the declared input_schema."""
        required = self.definition.input_schema.get("required", [])
        for field in required:
            if field not in params or params[field] is None:
                raise ValidationError(
                    f"Workflow [{self.name}] missing required input parameter [{field}].",
                    code="WINDAGENT_ERR_VALIDATION",
                    details={"workflow": self.name, "missing_field": field},
                )

    @abstractmethod
    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        """Builds the deterministic sequence of workflow steps."""
        pass
