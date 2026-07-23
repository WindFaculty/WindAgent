"""
High-Performance DAG Graph Utilities for Orchestration V2 Workflow Engine.
Provides O(V+E) iterative Kahn's algorithm cycle detection & topological sorting without recursion limits.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Tuple, Any
from windagent_core.errors.exceptions import DomainError
from windagent_orchestration.workflow_engine.definition import WorkflowDefinition


class DAGValidationError(DomainError):
    def __init__(self, message: str, details: Dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="WINDAGENT_ERR_DAG_VALIDATION",
            details=details or {},
        )


class WorkflowGraph:
    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self.nodes = definition.nodes
        self.adj_list: Dict[str, List[Tuple[str, str | None]]] = {nid: [] for nid in self.nodes}
        self.in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        self.incoming_edges: Dict[str, List[Tuple[str, str | None]]] = {nid: [] for nid in self.nodes}

        for edge in definition.edges:
            if edge.from_node_id not in self.nodes or edge.to_node_id not in self.nodes:
                raise DAGValidationError(
                    message=f"Dangling edge detected: [{edge.from_node_id}] -> [{edge.to_node_id}]",
                    details={"from": edge.from_node_id, "to": edge.to_node_id},
                )
            self.adj_list[edge.from_node_id].append((edge.to_node_id, edge.condition))
            self.incoming_edges[edge.to_node_id].append((edge.from_node_id, edge.condition))
            self.in_degree[edge.to_node_id] += 1

    def detect_cycles(self) -> None:
        """Iterative Kahn's algorithm for O(V+E) cycle detection without recursion limit."""
        in_deg = dict(self.in_degree)
        queue = deque([nid for nid, deg in in_deg.items() if deg == 0])
        visited_count = 0

        while queue:
            u = queue.popleft()
            visited_count += 1
            for v, _ in self.adj_list[u]:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    queue.append(v)

        if visited_count != len(self.nodes):
            raise DAGValidationError(
                message=f"Cycle detected in workflow graph: visited {visited_count}/{len(self.nodes)} nodes",
                details={"visited_count": visited_count, "total_nodes": len(self.nodes)},
            )

    def get_initial_ready_nodes(self) -> List[str]:
        """Returns all root nodes with zero in-degree."""
        return [nid for nid, deg in self.in_degree.items() if deg == 0]
