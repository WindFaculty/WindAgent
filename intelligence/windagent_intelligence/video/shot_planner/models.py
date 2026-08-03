"""
Phase 9 result types (plan 03 §16).

`ShotGraphReceipt` is the immutable result of `ShotGraphPlannerService.plan`:
the typed dependency graph, per-shot specifications (camera + generation mode
+ scheduling), graph issues, and the deterministic graph hash tied to the
source plan/package hashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.domain.video_production.shot import ShotDependencyGraph
from windagent_core.domain.video_production.shot_graph import (
    ShotGraphIssue,
    ShotScheduling,
    ShotSpecification,
)


@dataclass(frozen=True)
class ShotGraphReceipt:
    """Result of shot-graph planning — never a partial/invalid graph."""

    graph: ShotDependencyGraph
    specifications: List[ShotSpecification]
    scheduling: List[ShotScheduling]
    issues: List[ShotGraphIssue] = field(default_factory=list)
    graph_hash: str = ""
    source_plan_hash: str = ""
    source_package_hash: str = ""
    graph_version: str = "1.0.0"
    camera_rule_version: str = "1.0.0"
    generation_mode_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph": self.graph.model_dump(mode="json"),
            "specifications": [s.to_dict() for s in self.specifications],
            "scheduling": [s.to_dict() for s in self.scheduling],
            "issues": [i.to_dict() for i in self.issues],
            "graph_hash": self.graph_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_package_hash": self.source_package_hash,
            "graph_version": self.graph_version,
            "camera_rule_version": self.camera_rule_version,
            "generation_mode_version": self.generation_mode_version,
        }


__all__ = ["ShotGraphReceipt"]
