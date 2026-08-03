"""
Production scheduler for the Durable Production Workflow (plan 05 §8.4).

The scheduler decides which steps may START, respecting:

- the shot DAG (a shot cannot start before its dependency artifacts exist);
- approval gates (a step behind an unapproved gate is never scheduled);
- candidate / retry limits (bounded attempts per step, bounded candidate set);
- provider concurrency (Release 0.1: Flow concurrency is 1);
- the strict rule that the scheduler NEVER selects a candidate and NEVER
  approves anything — it only exposes readiness so the engine can execute.

The scheduler is pure and deterministic: given the same run facts it returns
the same ordering. It never performs external side effects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from windagent_core.errors.exceptions import ValidationError

from windagent_orchestration.production.approvals import ProductionApprovalGate
from windagent_orchestration.production.states import ProductionStepState


@dataclass(frozen=True)
class ProductionStepNode:
    """A step the scheduler can schedule."""

    step_id: str
    dependencies: Tuple[str, ...] = ()
    approval_gate: Optional[ProductionApprovalGate] = None
    external_cost: bool = False  # True = provider/credit consuming operation
    max_attempts: int = 3
    candidate_limit: Optional[int] = None


@dataclass
class SchedulerFacts:
    """Run facts the scheduler reads (never mutates)."""

    completed_steps: Set[str] = field(default_factory=set)
    in_flight_steps: Set[str] = field(default_factory=set)
    step_attempts: Dict[str, int] = field(default_factory=dict)
    approved_gates: Set[ProductionApprovalGate] = field(default_factory=set)
    revision_hash: str = ""
    cancelled: bool = False


@dataclass
class ScheduleDecision:
    step_id: str
    reason: str = "ready"


class ProductionScheduler:
    """Deterministic readiness scheduler (plan 05 §8.4)."""

    def __init__(
        self,
        *,
        provider_concurrency: int = 1,
        allow_parallel_no_cost: bool = True,
    ) -> None:
        if provider_concurrency < 1:
            raise ValidationError(
                "provider_concurrency must be >= 1",
                code="WINDAGENT_ERR_VALIDATION",
            )
        self.provider_concurrency = provider_concurrency
        self.allow_parallel_no_cost = allow_parallel_no_cost

    # -- public API -----------------------------------------------------------
    def ready_steps(
        self,
        nodes: List[ProductionStepNode],
        facts: SchedulerFacts,
    ) -> List[ScheduleDecision]:
        """Return the ordered set of steps that may start right now.

        Ordering is deterministic: dependency count then step_id (stable).
        Never mutates facts. A cancelled run yields no ready steps.
        """
        if facts.cancelled:
            return []

        by_id = {n.step_id: n for n in nodes}
        ready: List[ScheduleDecision] = []

        # Count currently-in-flight external (provider) operations.
        in_flight_external = sum(
            1
            for sid in facts.in_flight_steps
            if by_id.get(sid) is not None and by_id[sid].external_cost
        )

        for step_id in self._topological_order(nodes):
            node = by_id[step_id]
            if node.step_id in facts.completed_steps:
                continue
            if node.step_id in facts.in_flight_steps:
                continue

            # Dependency gate
            deps_ok = all(d in facts.completed_steps for d in node.dependencies)
            if not deps_ok:
                continue

            # Approval gate
            if node.approval_gate is not None:
                if node.approval_gate not in facts.approved_gates:
                    continue

            # Attempt budget
            attempts = facts.step_attempts.get(node.step_id, 0)
            if attempts >= node.max_attempts:
                continue

            # Provider concurrency (Release 0.1: 1)
            if node.external_cost and in_flight_external >= self.provider_concurrency:
                continue

            if node.external_cost:
                in_flight_external += 1
            ready.append(ScheduleDecision(node.step_id, reason="ready"))
        return ready

    def schedule_plan(self, nodes: List[ProductionStepNode], facts: SchedulerFacts) -> List[Dict[str, Any]]:
        """Simulate full plan scheduling (used by tests/verifier to prove the
        DAG resolves and gates gate). Returns per-step schedule records."""
        result: List[Dict[str, Any]] = []
        sim_completed: Set[str] = set()
        sim_attempts: Dict[str, int] = dict(facts.step_attempts)
        sim_approved: Set[ProductionApprovalGate] = set(facts.approved_gates)

        # Pre-populate already-completed steps from facts.
        for step in facts.completed_steps:
            sim_completed.add(step)

        for step_id in self._topological_order(nodes):
            node = by_id_step(nodes, step_id)
            if step_id in sim_completed:
                result.append({"step_id": step_id, "state": ProductionStepState.COMPLETED.value})
                continue
            deps_ok = all(d in sim_completed for d in node.dependencies)
            gate_ok = node.approval_gate is None or node.approval_gate in sim_approved
            attempts_ok = sim_attempts.get(step_id, 0) < node.max_attempts
            if not (deps_ok and gate_ok and attempts_ok):
                blocked_reason = "approval_pending" if not gate_ok else "dependencies_pending"
                result.append({"step_id": step_id, "state": "BLOCKED", "reason": blocked_reason})
                continue
            result.append({"step_id": step_id, "state": "SCHEDULED"})
            sim_completed.add(step_id)
            sim_attempts[step_id] = sim_attempts.get(step_id, 0) + 1

        return result

    # -- helpers ---------------------------------------------------------------
    def _topological_order(self, nodes: List[ProductionStepNode]) -> List[str]:
        """Stable topological order: dependency count, then step_id."""
        by_id = {n.step_id: n for n in nodes}
        indegree: Dict[str, int] = {n.step_id: len(n.dependencies) for n in nodes}
        dependents: Dict[str, List[str]] = {n.step_id: [] for n in nodes}
        for n in nodes:
            for dep in n.dependencies:
                if dep not in by_id:
                    raise ValidationError(
                        f"Step {n.step_id} depends on unknown step {dep}",
                        code="WINDAGENT_ERR_VALIDATION",
                        details={"step": n.step_id, "missing_dependency": dep},
                    )
                dependents[dep].append(n.step_id)

        ordered: List[str] = []
        queue = sorted(sid for sid, deg in indegree.items() if deg == 0)
        while queue:
            sid = queue.pop(0)
            ordered.append(sid)
            for child in sorted(dependents[sid]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(ordered) != len(nodes):
            raise ValidationError(
                "Workflow step graph contains a cycle",
                code="WINDAGENT_ERR_VALIDATION",
            )
        return ordered


def by_id_step(nodes: List[ProductionStepNode], step_id: str) -> ProductionStepNode:
    for n in nodes:
        if n.step_id == step_id:
            return n
    raise ValidationError(
        f"Unknown step {step_id}",
        code="WINDAGENT_ERR_VALIDATION",
    )


def scheduler_signature(
    nodes: List[ProductionStepNode],
    facts: SchedulerFacts,
) -> str:
    """Deterministic signature of a schedule decision (reuse/audit aid)."""
    decisions = ProductionScheduler().ready_steps(nodes, facts)
    payload = json.dumps(
        {
            "nodes": [
                {
                    "step_id": n.step_id,
                    "deps": list(n.dependencies),
                    "gate": n.approval_gate.value if n.approval_gate else None,
                    "external": n.external_cost,
                    "max_attempts": n.max_attempts,
                }
                for n in nodes
            ],
            "facts": {
                "completed": sorted(facts.completed_steps),
                "attempts": facts.step_attempts,
                "approved": sorted(g.value for g in facts.approved_gates),
            },
            "decisions": [d.step_id for d in decisions],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ProductionStepNode",
    "SchedulerFacts",
    "ScheduleDecision",
    "ProductionScheduler",
    "by_id_step",
    "scheduler_signature",
]
