"""
Core Workflow Engine for Orchestration V2.
Manages DAG execution, fan-out/fan-in node readiness, conditional edge evaluation, checkpoints, and resume.

DEPRECATED AUTHORITY (studio.contract/v0.1, authority rule 5): this engine may
serve existing non-Studio paths but must never receive Story tasks. Plan A
fences it: any node referencing the Studio namespace (``studio.`` /
``studio.story.*``) is rejected at run initialization. New Studio runs belong to
``OrchestratorService``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Set

from windagent_orchestration.workflow_engine.definition import WorkflowDefinition
from windagent_orchestration.workflow_engine.graph import WorkflowGraph
from windagent_orchestration.workflow_engine.checkpoints import CheckpointManager

logger = logging.getLogger("windagent.orchestration.workflow_engine")

# STORY-FENCE-START
# Fence (authority rule 5): these lines name the Studio namespace only to
# reject Story tasks in this legacy engine. Do not add Story logic here.
STORY_NAMESPACE_PREFIXES = ("studio.", "studio.story.")


def _assert_no_story_node(definition: WorkflowDefinition) -> None:
    """Reject Story task references inside a legacy workflow definition.

    Authority rule 5: ``WorkflowEngine`` receives no new Story imports, task
    types, states, or routes. A node whose id/name/tool_name uses the Studio
    namespace, or whose parameters reference a ``studio.story.*`` task type, is
    a Story node and is rejected before any run state is created.
    """
    for node_id, node in (definition.nodes or {}).items():
        markers = [node_id, node.name, node.tool_name]
        if any(str(marker).startswith(STORY_NAMESPACE_PREFIXES) for marker in markers):
            raise ValueError(
                f"Story task rejected by legacy WorkflowEngine: node '{node_id}' "
                f"uses Studio namespace {[m for m in markers if m]}"
            )
        param_values = [
            str(value) for value in (node.params or {}).values() if isinstance(value, (str, list, tuple))
        ]
        if any("studio.story." in value for value in param_values):
            raise ValueError(
                f"Story task rejected by legacy WorkflowEngine: node '{node_id}' "
                "parameters reference a studio.story.* task type"
            )
# STORY-FENCE-END


class WorkflowEngine:
    """Legacy DAG engine — existing paths only; rejects new Story tasks."""

    def __init__(self, checkpoint_manager: Optional[CheckpointManager] = None, uow_factory: Optional[Any] = None):
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.uow_factory = uow_factory or getattr(self.checkpoint_manager, "uow_factory", None)
        self._active_runs: Dict[str, Dict[str, Any]] = {}

    def initialize_run(self, run_id: str, definition: WorkflowDefinition) -> Dict[str, Any]:
        _assert_no_story_node(definition)
        graph = WorkflowGraph(definition)
        graph.detect_cycles()

        initial_ready = graph.get_initial_ready_nodes()
        run_state = {
            "run_id": run_id,
            "definition": definition,
            "graph": graph,
            "completed_results": {},
            "failed_nodes": {},
            "cursor": 0,
            "status": "running",
            "ready_nodes": set(initial_ready),
            "in_flight_nodes": set(),
        }
        self._active_runs[run_id] = run_state
        logger.info(f"Initialized workflow run [{run_id}] with initial ready nodes: {initial_ready}")
        return run_state

    def get_ready_nodes(self, run_id: str) -> List[str]:
        state = self._active_runs.get(run_id)
        if not state:
            return []
        return list(state["ready_nodes"] - state["in_flight_nodes"])

    def mark_node_dispatched(self, run_id: str, node_id: str) -> None:
        state = self._active_runs.get(run_id)
        if state and node_id in state["ready_nodes"]:
            state["ready_nodes"].remove(node_id)
            state["in_flight_nodes"].add(node_id)

    async def complete_node(
        self,
        run_id: str,
        node_id: str,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        state = self._active_runs.get(run_id)
        if not state:
            return []

        state["in_flight_nodes"].discard(node_id)
        state["completed_results"][node_id] = result
        state["cursor"] += 1

        graph: WorkflowGraph = state["graph"]
        newly_ready: List[str] = []

        # Evaluate downstream child nodes (fan-out)
        for downstream_id, condition_expr in graph.adj_list.get(node_id, []):
            # Check conditional edge if specified
            if condition_expr:
                cond_pass = result.get("status") == "success" and result.get(condition_expr, True)
                if not cond_pass:
                    logger.info(f"Conditional edge [{node_id}] -> [{downstream_id}] evaluated false. Skipping [{downstream_id}].")
                    continue

            # Check fan-in gate: all parents of downstream_id must be completed
            parents = graph.incoming_edges.get(downstream_id, [])
            all_parents_complete = all(p_id in state["completed_results"] for p_id, _ in parents)
            if all_parents_complete:
                newly_ready.append(downstream_id)
                state["ready_nodes"].add(downstream_id)

        # Create checkpoint
        ckpt_id = str(uuid.uuid4())
        await self.checkpoint_manager.save_checkpoint(
            checkpoint_id=ckpt_id,
            run_id=run_id,
            step_id=node_id,
            cursor=state["cursor"],
            completed_steps=state["completed_results"],
            context_data=context or {},
        )

        # Check if workflow is complete
        if len(state["completed_results"]) == len(graph.nodes):
            state["status"] = "completed"
            logger.info(f"Workflow run [{run_id}] completed all {len(graph.nodes)} nodes.")

        return newly_ready

    async def resume_from_checkpoint(self, run_id: str, definition: WorkflowDefinition) -> Dict[str, Any]:
        ckpt = await self.checkpoint_manager.load_latest_checkpoint(run_id)
        run_state = self.initialize_run(run_id, definition)
        if not ckpt:
            return run_state

        run_state["completed_results"] = ckpt.completed_steps
        run_state["cursor"] = ckpt.cursor

        # Re-evaluate ready nodes based on completed steps
        graph: WorkflowGraph = run_state["graph"]
        ready_set: Set[str] = set()

        for nid in graph.nodes:
            if nid in run_state["completed_results"]:
                continue
            parents = graph.incoming_edges.get(nid, [])
            if not parents or all(p_id in run_state["completed_results"] for p_id, _ in parents):
                ready_set.add(nid)

        run_state["ready_nodes"] = ready_set
        logger.info(f"Resumed workflow run [{run_id}] from cursor [{ckpt.cursor}] with ready nodes: {list(ready_set)}")
        return run_state
