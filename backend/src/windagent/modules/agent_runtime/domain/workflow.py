"""Workflow DAG definition + validator (Phase 13).

REWRITE of ``windagent_core.domain.workflow`` and
``workflow_engine.graph/validator``.  Nodes, edges, and definition are
immutable Pydantic models; validation ensures acyclic DAG, unknown refs, and
duplicate ids are rejected before persistence.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeWorkflowError


class WorkflowNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tool_name: str = Field(default="", description="Tool or agent capability to execute")
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=3, ge=1)

    @field_validator("id", "name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeWorkflowError("Workflow node id/name cannot be blank.")
        return v.strip()


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_node_id: str = Field(min_length=1)
    to_node_id: str = Field(min_length=1)
    condition: str | None = None
    edge_type: str = Field(default="dependency")

    @field_validator("from_node_id", "to_node_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeWorkflowError("Edge node id cannot be blank.")
        return v.strip()


class WorkflowDefinition(BaseModel):
    """Immutable DAG definition.  ``nodes`` keyed by id, ``edges`` as list."""

    model_config = ConfigDict(frozen=True, extra="allow")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    nodes: dict[str, WorkflowNode] = Field(default_factory=dict)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @field_validator("id", "name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeWorkflowError("Workflow id/name cannot be blank.")
        return v.strip()

    def validate_dag(self) -> None:
        """Raise ``AgentRuntimeWorkflowError`` if DAG is invalid."""
        if not self.nodes:
            raise AgentRuntimeWorkflowError("Workflow must have at least one node.", context={"workflow_id": self.id})
        # Unknown refs
        for edge in self.edges:
            if edge.from_node_id not in self.nodes:
                raise AgentRuntimeWorkflowError(
                    f"Edge references unknown from_node {edge.from_node_id!r}.",
                    context={"workflow_id": self.id, "edge": edge.model_dump()},
                )
            if edge.to_node_id not in self.nodes:
                raise AgentRuntimeWorkflowError(
                    f"Edge references unknown to_node {edge.to_node_id!r}.",
                    context={"workflow_id": self.id, "edge": edge.model_dump()},
                )
            if edge.from_node_id == edge.to_node_id:
                raise AgentRuntimeWorkflowError(
                    "Self-loop edge is not allowed.", context={"workflow_id": self.id, "node_id": edge.from_node_id}
                )
        # Duplicate edges (same from->to)
        seen: set[tuple[str, str]] = set()
        for edge in self.edges:
            key = (edge.from_node_id, edge.to_node_id)
            if key in seen:
                raise AgentRuntimeWorkflowError(
                    f"Duplicate edge {edge.from_node_id!r} -> {edge.to_node_id!r}.",
                    context={"workflow_id": self.id},
                )
            seen.add(key)
        # Cycle detection (Kahn)
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            adj[edge.from_node_id].append(edge.to_node_id)
            in_degree[edge.to_node_id] += 1
        queue: deque[str] = deque([nid for nid, deg in in_degree.items() if deg == 0])
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for nxt in adj[node]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        if visited != len(self.nodes):
            raise AgentRuntimeWorkflowError(
                "Workflow graph contains a cycle.", context={"workflow_id": self.id}
            )

    def topological_order(self) -> list[str]:
        """Return node ids in topological order; raises if cyclic."""
        self.validate_dag()
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            adj[edge.from_node_id].append(edge.to_node_id)
            in_degree[edge.to_node_id] += 1
        queue: deque[str] = deque(sorted([nid for nid, deg in in_degree.items() if deg == 0]))
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in sorted(adj[node]):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        return order

    def ready_nodes(self, completed: frozenset[str]) -> list[WorkflowNode]:
        """Nodes whose predecessors are all completed and not yet completed themselves."""
        preds: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for edge in self.edges:
            preds[edge.to_node_id].add(edge.from_node_id)
        ready: list[WorkflowNode] = []
        for nid, node in self.nodes.items():
            if nid in completed:
                continue
            if preds[nid].issubset(completed):
                ready.append(node)
        # Priority order then id
        ready.sort(key=lambda n: (-n.priority, n.id))
        return ready


__all__ = ["WorkflowDefinition", "WorkflowEdge", "WorkflowNode"]
