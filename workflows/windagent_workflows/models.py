"""
Enhanced Workflow Models for WindAgent Workflow Packs (Phase 23).
Provides immutable workflow definitions with:
- ArtifactContracts for each step (expected outputs)
- CompletionPredicates for step completion validation
- Fan-out / Fan-in support via WorkflowNodeSpec.node_type
- Conditional edges with expressions
- Semantic versioning
"""

from __future__ import annotations
import copy
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from windagent_core.errors.exceptions import ValidationError


class NodeType(str, Enum):
    TASK = "task"           # Standard execution step
    FAN_OUT = "fan_out"     # Branching point (parallel execution)
    FAN_IN = "fan_in"       # Merge point (synchronization)
    GATEWAY = "gateway"     # Conditional routing
    SUB_WORKFLOW = "sub_workflow"  # Nested workflow


class EdgeType(str, Enum):
    DEPENDENCY = "dependency"       # Standard sequential dependency
    CONDITIONAL = "conditional"     # Conditional execution (requires expression)
    DEFAULT = "default"             # Default path when no condition matches
    PARALLEL = "parallel"           # Fan-out parallel execution


@dataclass(frozen=True)
class ArtifactContract:
    """Expected input/output artifact for a workflow step."""
    name: str
    description: str = ""
    required: bool = True
    mime_type: Optional[str] = None
    schema_ref: Optional[str] = None  # JSON schema reference for validation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "mime_type": self.mime_type,
            "schema_ref": self.schema_ref,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ArtifactContract:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            required=bool(data.get("required", True)),
            mime_type=data.get("mime_type"),
            schema_ref=data.get("schema_ref"),
        )


@dataclass(frozen=True)
class CompletionPredicate:
    """Predicate that determines when a workflow step is considered complete."""
    type: str = "always"  # always, tool_success, output_match, condition, artifact_exists
    expression: Optional[str] = None  # Expression for output_match/condition types
    expected_exit_code: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "expression": self.expression,
            "expected_exit_code": self.expected_exit_code,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CompletionPredicate:
        return cls(
            type=str(data.get("type", "always")),
            expression=data.get("expression"),
            expected_exit_code=int(data.get("expected_exit_code", 0)),
        )


@dataclass(frozen=True)
class WorkflowNodeSpec:
    """Immutable specification for a single workflow node."""
    id: str
    name: str
    tool_name: str
    node_type: NodeType = NodeType.TASK
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[float] = None
    max_attempts: int = 3
    priority: int = 0
    input_artifacts: List[ArtifactContract] = field(default_factory=list)
    output_artifacts: List[ArtifactContract] = field(default_factory=list)
    completion_predicate: CompletionPredicate = field(default_factory=CompletionPredicate)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tool_name": self.tool_name,
            "node_type": self.node_type.value,
            "params": self.params,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "priority": self.priority,
            "input_artifacts": [a.to_dict() for a in self.input_artifacts],
            "output_artifacts": [a.to_dict() for a in self.output_artifacts],
            "completion_predicate": self.completion_predicate.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowNodeSpec:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            tool_name=str(data.get("tool_name", "")),
            node_type=NodeType(data.get("node_type", "task")),
            params=data.get("params", {}),
            timeout_seconds=data.get("timeout_seconds"),
            max_attempts=int(data.get("max_attempts", 3)),
            priority=int(data.get("priority", 0)),
            input_artifacts=[ArtifactContract.from_dict(a) for a in data.get("input_artifacts", [])],
            output_artifacts=[ArtifactContract.from_dict(a) for a in data.get("output_artifacts", [])],
            completion_predicate=CompletionPredicate.from_dict(data.get("completion_predicate", {})),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class WorkflowEdgeSpec:
    """Immutable specification for a directed edge between nodes."""
    from_node_id: str
    to_node_id: str
    edge_type: EdgeType = EdgeType.DEPENDENCY
    condition_expression: Optional[str] = None  # For conditional edges
    label: Optional[str] = None  # Human-readable label

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type.value,
            "condition_expression": self.condition_expression,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowEdgeSpec:
        return cls(
            from_node_id=str(data.get("from_node_id", "")),
            to_node_id=str(data.get("to_node_id", "")),
            edge_type=EdgeType(data.get("edge_type", "dependency")),
            condition_expression=data.get("condition_expression"),
            label=data.get("label"),
        )


@dataclass(frozen=True)
class ImmutableWorkflowDefinition:
    """Fully immutable workflow definition with versioning, DAG structure, and artifact contracts.
    Once created, this cannot be modified — any changes produce a new version.
    """
    id: str
    name: str
    semantic_version: str  # e.g. "1.0.0"
    description: str = ""
    nodes: Dict[str, WorkflowNodeSpec] = field(default_factory=dict)
    edges: List[WorkflowEdgeSpec] = field(default_factory=list)
    input_artifacts: List[ArtifactContract] = field(default_factory=list)
    output_artifacts: List[ArtifactContract] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Deterministic hash of the entire definition for identity comparison.
        Builds the dict without calling to_dict() to avoid recursion.
        """
        raw = json.dumps({
            "id": self.id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "description": self.description,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "input_artifacts": [a.to_dict() for a in self.input_artifacts],
            "output_artifacts": [a.to_dict() for a in self.output_artifacts],
            "metadata": self.metadata,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "description": self.description,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "input_artifacts": [a.to_dict() for a in self.input_artifacts],
            "output_artifacts": [a.to_dict() for a in self.output_artifacts],
            "metadata": self.metadata,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        nodes_raw = data.get("nodes", {})
        edges_raw = data.get("edges", [])
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            semantic_version=str(data.get("semantic_version", "1.0.0")),
            description=str(data.get("description", "")),
            nodes={nid: WorkflowNodeSpec.from_dict(n) for nid, n in nodes_raw.items()},
            edges=[WorkflowEdgeSpec.from_dict(e) for e in edges_raw],
            input_artifacts=[ArtifactContract.from_dict(a) for a in data.get("input_artifacts", [])],
            output_artifacts=[ArtifactContract.from_dict(a) for a in data.get("output_artifacts", [])],
            metadata=data.get("metadata", {}),
        )

    def get_initial_nodes(self) -> List[WorkflowNodeSpec]:
        """Returns all root nodes (no incoming dependency edges)."""
        has_incoming: Set[str] = set()
        for edge in self.edges:
            if edge.edge_type in (EdgeType.DEPENDENCY, EdgeType.CONDITIONAL, EdgeType.DEFAULT):
                has_incoming.add(edge.to_node_id)
        return [n for nid, n in self.nodes.items() if nid not in has_incoming]

    def get_downstream(self, node_id: str) -> List[WorkflowEdgeSpec]:
        """Returns all outgoing edges from a node."""
        return [e for e in self.edges if e.from_node_id == node_id]

    def get_upstream(self, node_id: str) -> List[WorkflowEdgeSpec]:
        """Returns all incoming edges to a node."""
        return [e for e in self.edges if e.to_node_id == node_id]

    def validate(self) -> None:
        """Validates the workflow definition structure."""
        errors = []

        if not self.id:
            errors.append("Workflow ID cannot be empty")
        if not self.name:
            errors.append("Workflow name cannot be empty")
        if not self.semantic_version:
            errors.append("Semantic version cannot be empty")

        # Check all node references in edges exist
        node_ids = set(self.nodes.keys())
        for edge in self.edges:
            if edge.from_node_id not in node_ids:
                errors.append(f"Edge from_node [{edge.from_node_id}] references non-existent node")
            if edge.to_node_id not in node_ids:
                errors.append(f"Edge to_node [{edge.to_node_id}] references non-existent node")

        # Check conditional edges have expressions
        for edge in self.edges:
            if edge.edge_type == EdgeType.CONDITIONAL and not edge.condition_expression:
                errors.append(f"Conditional edge [{edge.from_node_id} -> {edge.to_node_id}] missing condition_expression")

        # Check fan-out nodes have PARALLEL edges
        for nid, node in self.nodes.items():
            if node.node_type == NodeType.FAN_OUT:
                outgoing = self.get_downstream(nid)
                parallel_edges = [e for e in outgoing if e.edge_type == EdgeType.PARALLEL]
                if not parallel_edges:
                    errors.append(f"Fan-out node [{nid}] has no parallel outgoing edges")

        if errors:
            raise ValidationError(
                message="Workflow definition validation failed",
                code="WINDAGENT_ERR_WORKFLOW_VALIDATION",
                details={"errors": errors},
            )
