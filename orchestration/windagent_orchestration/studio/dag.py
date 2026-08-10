"""Deterministic Studio story DAG builder (Plan A — A4, studio.contract/v0.1).

Builds the frozen Story DAG over the A2 task types and lifecycle checkpoints.
Determinism contract: the same (episode, revision, policy) always produces the
identical DAG JSON — node ids, dependency edges, gate placement, and topo
order are structural, never time- or storage-derived. The DAG is persisted in
``studio_runs.dag_json`` BEFORE any durable submission.

Approval gates: the LAST node of a stage carries the stage checkpoint and a
``gate`` flag. With ``gate=true`` the orchestrator parks that node in
WAITING_APPROVAL when it completes; only ``record_approval`` (APPROVED)
resumes its dependents. ``gate=false`` (checkpoint mode AUTO) advances the
DAG immediately.

The REVIEW/REVISE/LOCK task types exist in the frozen catalog; revision loops
and the lock step are driven by B-phase handlers through the same durable
path. This builder emits the canonical linear pipeline; rejection at a gate
is a durable FAILED run (a new run over a derived revision is the B-phase
revision workflow).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.studio.approval import ApprovalPolicy
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
from windagent_core.contracts.studio.ids import EpisodeId, ProductionRevisionId
from windagent_core.contracts.studio.models import StudioNodeStatus, StudioTaskType

STUDIO_DAG_SCHEMA_VERSION = "studio.dag/v1"

# Canonical node ids: stable across runs, episodes, and policies.
NODE_IDEA_GENERATE = "idea.generate"
NODE_IDEA_EVALUATE = "idea.evaluate"
NODE_BIBLE_GENERATE = "bible.generate"
NODE_BEATS_GENERATE = "beats.generate"
NODE_OUTLINE_GENERATE = "outline.generate"
NODE_SCREENPLAY_GENERATE = "screenplay.generate"
NODE_REVIEW = "review"
NODE_LOCK = "lock"

# node id -> (task type, approval checkpoint of the stage, if any)
_PIPELINE: List[tuple[str, StudioTaskType, Optional[ApprovalCheckpoint]]] = [
    (NODE_IDEA_GENERATE, StudioTaskType.IDEA_GENERATE, None),
    (NODE_IDEA_EVALUATE, StudioTaskType.IDEA_EVALUATE, ApprovalCheckpoint.IDEA),
    (NODE_BIBLE_GENERATE, StudioTaskType.BIBLE_GENERATE, ApprovalCheckpoint.STORY_BIBLE),
    (NODE_BEATS_GENERATE, StudioTaskType.BEATS_GENERATE, None),
    (NODE_OUTLINE_GENERATE, StudioTaskType.OUTLINE_GENERATE, ApprovalCheckpoint.OUTLINE),
    (NODE_SCREENPLAY_GENERATE, StudioTaskType.SCREENPLAY_GENERATE, None),
    (NODE_REVIEW, StudioTaskType.REVIEW, ApprovalCheckpoint.SCREENPLAY),
    (NODE_LOCK, StudioTaskType.LOCK, None),
]


def _gate_active(policy: ApprovalPolicy, checkpoint: Optional[ApprovalCheckpoint]) -> bool:
    if checkpoint is None:
        return False
    return policy.mode_for(checkpoint) != ApprovalMode.AUTO


def build_story_dag(
    *,
    episode_id: EpisodeId,
    revision_id: Optional[ProductionRevisionId],
    policy: ApprovalPolicy,
) -> Dict[str, Any]:
    """Deterministic DAG over the frozen pipeline; identical input -> identical JSON."""
    nodes: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    previous: Optional[str] = None
    for node_id, task_type, checkpoint in _PIPELINE:
        nodes[node_id] = {
            "task_type": task_type.value,
            "depends_on": [previous] if previous is not None else [],
            "checkpoint": checkpoint.value if checkpoint is not None else None,
            "gate": _gate_active(policy, checkpoint),
        }
        order.append(node_id)
        previous = node_id
    return {
        "schema_version": STUDIO_DAG_SCHEMA_VERSION,
        "episode_id": str(episode_id),
        "revision_id": str(revision_id) if revision_id is not None else None,
        "nodes": nodes,
        "order": order,
    }


def initial_node_states(dag: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Durable initial per-node rows: roots RUNNABLE, the rest PENDING."""
    nodes = dag["nodes"]
    states: Dict[str, Dict[str, Any]] = {}
    for node_id, node in nodes.items():
        states[node_id] = {
            "task_type": node["task_type"],
            "depends_on": list(node.get("depends_on", [])),
            "checkpoint": node.get("checkpoint"),
            "gate": bool(node.get("gate", False)),
            "status": (
                StudioNodeStatus.RUNNABLE.value
                if not node.get("depends_on")
                else StudioNodeStatus.PENDING.value
            ),
            "attempt": 1,
        }
    return states


def dependencies_terminal(node: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, Any]]) -> bool:
    """True when every dependency of ``node`` is in a terminal state."""
    for dep_id in node.get("depends_on", []):
        dep = nodes_by_id.get(dep_id)
        if dep is None or dep.get("status") not in StudioNodeStatus.terminal():
            return False
    return True


def next_checkpoint(
    checkpoint: Optional[str],
) -> Optional[str]:
    """The approval checkpoint that follows ``checkpoint`` in the frozen order."""
    if checkpoint is None:
        return None
    order = list(ApprovalCheckpoint)
    try:
        index = order.index(ApprovalCheckpoint(checkpoint))
    except ValueError:
        return None
    if index + 1 >= len(order):
        return None
    return order[index + 1].value


__all__ = [
    "STUDIO_DAG_SCHEMA_VERSION",
    "NODE_IDEA_GENERATE",
    "NODE_IDEA_EVALUATE",
    "NODE_BIBLE_GENERATE",
    "NODE_BEATS_GENERATE",
    "NODE_OUTLINE_GENERATE",
    "NODE_SCREENPLAY_GENERATE",
    "NODE_REVIEW",
    "NODE_LOCK",
    "build_story_dag",
    "initial_node_states",
    "dependencies_terminal",
    "next_checkpoint",
]
