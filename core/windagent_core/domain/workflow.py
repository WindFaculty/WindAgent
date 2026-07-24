"""
Canonical Graph Workflow Definition Models for WindAgent Domain Core (Phase 8).
Supports nodes, dependency edges, conditional edges, priority, and graph validation.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.types import WorkflowId, StepId


class WorkflowNode(BaseModel):
    """Canonical workflow step node within a workflow DAG."""
    id: str
    name: str
    tool_name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    timeout_seconds: Optional[float] = None
    max_attempts: int = 3

    model_config = ConfigDict(frozen=False, extra="allow")


class WorkflowEdge(BaseModel):
    """Dependency or conditional execution edge between workflow nodes."""
    from_node_id: str
    to_node_id: str
    condition: Optional[str] = None
    edge_type: str = "dependency"

    model_config = ConfigDict(frozen=False, extra="allow")


class WorkflowDefinition(BaseModel):
    """Canonical Graph DAG Workflow Definition."""
    id: str
    name: str
    version: int = 1
    nodes: Dict[str, WorkflowNode] = Field(default_factory=dict)
    edges: List[WorkflowEdge] = Field(default_factory=list)

    model_config = ConfigDict(frozen=False, extra="allow")

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, from_id: str, to_id: str, condition: Optional[str] = None) -> None:
        self.edges.append(WorkflowEdge(from_node_id=from_id, to_node_id=to_id, condition=condition))
