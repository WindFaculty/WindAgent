"""
Fast DAG Validator for Orchestration V2 Engine.
Enforces performance gate targets:
- 1,000 nodes validation <= 50 ms
- 10,000 nodes validation <= 500 ms
"""

from __future__ import annotations

import time
from typing import Dict, List, Any
from windagent_orchestration.workflow_engine.definition import WorkflowDefinition, WorkflowNode, WorkflowEdge
from windagent_orchestration.workflow_engine.graph import WorkflowGraph


class WorkflowValidator:
    @staticmethod
    def validate_definition(definition: WorkflowDefinition) -> float:
        """Validates DAG structure and returns validation duration in milliseconds."""
        t0 = time.perf_counter()
        graph = WorkflowGraph(definition)
        graph.detect_cycles()
        duration_ms = (time.perf_counter() - t0) * 1000.0
        return duration_ms

    @staticmethod
    def validate_nodes_and_edges(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> float:
        wf = WorkflowDefinition(id="val_test", name="Validation Workflow")
        for n in nodes:
            wf.add_node(WorkflowNode(id=n["id"], name=n.get("name", n["id"]), tool_name=n.get("tool_name", "noop")))
        for e in edges:
            wf.add_edge(from_id=e["from"], to_id=e["to"], condition=e.get("condition"))

        return WorkflowValidator.validate_definition(wf)
