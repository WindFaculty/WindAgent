"""
Workflow Definition Domain Models for Orchestration V2 Engine.
Supports nodes, dependency edges, conditional edges, fan-out, and fan-in gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable


@dataclass
class WorkflowNode:
    id: str
    name: str
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 2


@dataclass
class WorkflowEdge:
    from_node_id: str
    to_node_id: str
    condition: Optional[str] = None  # None = unconditional execution edge


@dataclass
class WorkflowDefinition:
    id: str
    name: str
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    edges: List[WorkflowEdge] = field(default_factory=list)

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, from_id: str, to_id: str, condition: Optional[str] = None) -> None:
        self.edges.append(WorkflowEdge(from_node_id=from_id, to_node_id=to_id, condition=condition))
