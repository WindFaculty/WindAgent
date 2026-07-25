"""
Workflow Pack Contract & Base Implementation for WindAgent Architecture V2 (Phase 23).
Declares enhanced WorkflowPackDefinition and BaseWorkflowPack interface with:
- Semantic versioning
- Immutable DAG-based workflow definitions
- Conditional edges, fan-out/fan-in
- Artifact contracts
- Completion predicates
- Tool, model, permission, retry, checkpoint, and verification policies
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.domain.models import WorkflowStep
from windagent_core.errors.exceptions import ValidationError
from windagent_workflows.models import (
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, NodeType, EdgeType,
)


@dataclass
class WorkflowPackDefinition:
    name: str
    description: str
    semantic_version: str = "1.0.0"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    classification_rules: List[str] = field(default_factory=list)
    planning_policy: Dict[str, Any] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    optional_tools: List[str] = field(default_factory=list)
    model_requirements: Dict[str, Any] = field(default_factory=dict)
    permission_policy: Dict[str, Any] = field(default_factory=dict)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    checkpoint_policy: Dict[str, Any] = field(default_factory=dict)
    verification_policy: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: List[str] = field(default_factory=list)
    report_schema: Dict[str, Any] = field(default_factory=dict)
    report_format: str = "markdown"
    input_artifacts: List[ArtifactContract] = field(default_factory=list)
    output_artifacts: List[ArtifactContract] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationError("Workflow pack name cannot be empty.")
        if not self.acceptance_criteria:
            raise ValidationError(f"Workflow pack [{self.name}] must declare acceptance criteria.")
        if not self.semantic_version:
            raise ValidationError(f"Workflow pack [{self.name}] must declare a semantic_version.")


class BaseWorkflowPack(ABC):
    def __init__(self, definition: WorkflowPackDefinition):
        definition.validate()
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def version(self) -> str:
        return self.definition.semantic_version

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

    # ------------------------------------------------------------------
    # Legacy step sequence builder (backward compatible)
    # ------------------------------------------------------------------

    @abstractmethod
    def build_step_sequence(self, params: Dict[str, Any]) -> List[WorkflowStep]:
        """Builds the deterministic sequence of workflow steps.
        Legacy method — new packs should override build_workflow_definition() instead.
        """
        pass

    # ------------------------------------------------------------------
    # New: Immutable DAG workflow definition builder
    # ------------------------------------------------------------------

    def build_workflow_definition(self, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        """Builds an immutable DAG workflow definition.
        Override this method to provide DAG-based definitions with:
        - Conditional edges
        - Fan-out / fan-in nodes
        - Artifact contracts
        - Completion predicates
        
        Default implementation creates a linear DAG from build_step_sequence().
        """
        steps = self.build_step_sequence(params)
        nodes: Dict[str, WorkflowNodeSpec] = {}
        edges: List[WorkflowEdgeSpec] = []
        previous_id: Optional[str] = None

        for step in steps:
            node_id = f"step_{step.order}_{step.name}"
            node = WorkflowNodeSpec(
                id=node_id,
                name=step.name,
                tool_name=step.tool_name,
                params=step.params,
                completion_predicate=CompletionPredicate(type="tool_success"),
            )
            nodes[node_id] = node

            if previous_id:
                edges.append(WorkflowEdgeSpec(
                    from_node_id=previous_id,
                    to_node_id=node_id,
                    edge_type=EdgeType.DEPENDENCY,
                ))
            previous_id = node_id

        definition = ImmutableWorkflowDefinition(
            id=f"{self.name}_{self.definition.semantic_version}",
            name=self.name,
            semantic_version=self.definition.semantic_version,
            description=self.definition.description,
            nodes=nodes,
            edges=edges,
            input_artifacts=self.definition.input_artifacts,
            output_artifacts=self.definition.output_artifacts,
        )
        definition.validate()
        return definition
