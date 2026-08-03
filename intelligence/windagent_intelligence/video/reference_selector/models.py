"""
Phase 11 — Reference binding result types (plan 03 §24.1).

`ReferenceBindingPlanReceipt` is the immutable result of
`ReferenceBindingPlanner.plan`: the full binding plan (every shot's approved
asset bindings with roles, hashes, and revision), the deterministic binding
hash tied to the source graph/plan/package hashes, and the typed binding
issues. A blocking binding issue means the shot can NEVER compile into a
GenerationRequest — the planner fails closed by raising `ValidationFailureError`
when a blocking defect exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.domain.video_production.reference_binding import (
    ReferenceBindingIssue,
    ReferenceBindingPlan,
)


@dataclass(frozen=True)
class ReferenceBindingPlanReceipt:
    """Result of reference binding planning — never a partial plan."""

    plan: ReferenceBindingPlan
    issues: List[ReferenceBindingIssue] = field(default_factory=list)
    binding_hash: str = ""
    source_graph_hash: str = ""
    source_plan_hash: str = ""
    source_package_hash: str = ""
    binding_version: str = "1.0.0"

    @property
    def blocking_issues(self) -> List[ReferenceBindingIssue]:
        return [i for i in self.issues if i.blocking]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "binding_hash": self.binding_hash,
            "source_graph_hash": self.source_graph_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_package_hash": self.source_package_hash,
            "binding_version": self.binding_version,
        }


__all__ = ["ReferenceBindingPlanReceipt"]
