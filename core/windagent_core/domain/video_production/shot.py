"""
Shot planning aggregates: CinematicPlan, Shot, ShotDependency, and the
ShotDependencyGraph (road_map.md Phase 9).

Shots carry an explicit `order` integer within their scene; dependencies are
typed edges between shot IDs. The graph must stay acyclic for scheduling.

Phase 9 semantics (plan 03 §12-§16):
- every dependency edge records `dependency_type`, `required_artifact_type`,
  `reason` and `blocking`;
- the blocking subgraph must stay acyclic (fail closed);
- `topological_order()` is deterministic so scheduling is reproducible;
- `independent_shot_ids()` marks shots with no blocking predecessor so the
  orchestrator can run them in parallel (concurrency hint only).
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CameraMovement,
    DependencyType,
    RequiredArtifactType,
    ShotType,
    TransitionType,
)
from windagent_core.domain.video_production.errors import (
    ShotDependencyGraphCycleError,
)
from windagent_core.domain.video_production.ids import (
    CinematicPlanId,
    DialogueLineId,
    ProductionRevisionId,
    ReferenceAssetId,
    SceneId,
    ShotDependencyId,
    ShotId,
    VideoProjectId,
)


class Shot(BaseModel):
    """A single camera shot within a scene."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shot_id: ShotId
    scene_id: SceneId
    order: int = Field(ge=1)
    shot_type: ShotType = ShotType.MEDIUM
    camera_movement: CameraMovement = CameraMovement.STATIC
    duration_seconds: float = Field(gt=0)
    framing_description: str = ""
    transition_type: TransitionType = TransitionType.CUT
    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ShotDependency(BaseModel):
    """Typed dependency edge between two shots (Phase 9 semantics).

    Fields follow plan 03 §13: predecessor/successor shot IDs, dependency
    type, required artifact type, reason, and whether the edge is blocking
    (successor cannot start until the predecessor produced the artifact).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    dependency_id: ShotDependencyId
    from_shot_id: ShotId
    to_shot_id: ShotId
    dependency_type: DependencyType = DependencyType.TEMPORAL
    required_artifact_type: RequiredArtifactType = RequiredArtifactType.NONE
    reason: str = ""
    blocking: bool = False


class ShotDependencyGraph(BaseModel):
    """Directed acyclic graph over shots for scheduling (Phase 9)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shots: List[Shot] = Field(default_factory=list)
    dependencies: List[ShotDependency] = Field(default_factory=list)

    def shot_ids(self) -> List[ShotId]:
        return [s.shot_id for s in self.shots]

    def ordered_shot_ids(self) -> List[ShotId]:
        """Shots ordered by (scene order, shot order) using stable sort keys."""
        return [
            s.shot_id
            for s in sorted(self.shots, key=lambda s: (str(s.scene_id), s.order))
        ]

    def dependencies_of(self, shot_id: ShotId) -> List[ShotDependency]:
        """Outgoing edges from a shot (successors depend on this shot)."""
        return [d for d in self.dependencies if d.from_shot_id == shot_id]

    def dependencies_into(self, shot_id: ShotId) -> List[ShotDependency]:
        """Incoming edges into a shot (this shot depends on predecessors)."""
        return [d for d in self.dependencies if d.to_shot_id == shot_id]

    def blocking_edges(self) -> List[ShotDependency]:
        """Only edges that block the successor until the artifact is ready."""
        return [d for d in self.dependencies if d.blocking]

    def has_cycle(self) -> bool:
        """True if the graph contains any directed cycle."""
        return len(self._topological_sort()) < len(self.shots)

    def blocking_subgraph_has_cycle(self) -> bool:
        """True if the blocking subgraph (blocking edges only) has a cycle.

        Plan §13: the blocking subgraph must never cycle; non-blocking edges
        are advisory so they are excluded from the fail-closed check.
        """
        nodes = {str(s.shot_id) for s in self.shots}
        blocking = [d for d in self.dependencies if d.blocking]
        if not blocking:
            return False
        adjacency: Dict[str, List[str]] = {n: [] for n in nodes}
        for dep in blocking:
            adjacency.setdefault(str(dep.from_shot_id), []).append(str(dep.to_shot_id))

        visited: set = set()
        stack: set = set()

        def visit(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False
            stack.add(node)
            for nxt in adjacency.get(node, []):
                if nxt in nodes and visit(nxt):
                    return True
            stack.discard(node)
            visited.add(node)
            return False

        return any(visit(n) for n in nodes)

    def topological_order(self) -> List[ShotId]:
        """Deterministic topological order of all shots (Kahn, stable keys).

        Tie-breaking uses the shot's (scene, order) key so the order is
        reproducible across runs. Fails closed on a cycle by raising the
        typed `ShotDependencyGraphCycleError` instead of returning a partial
        order — callers must validate first (fail closed).
        """
        result = self._topological_sort()
        if len(result) < len(self.shots):
            raise ShotDependencyGraphCycleError(
                "ShotDependencyGraph contains a cycle; no topological order.",
                details={"shot_count": len(self.shots), "ordered_count": len(result)},
            )
        return result

    def independent_shot_ids(self) -> List[ShotId]:
        """Shots with no blocking predecessor (can be generated in parallel)."""
        blocked = {str(d.to_shot_id) for d in self.blocking_edges()}
        return [s.shot_id for s in self.shots if str(s.shot_id) not in blocked]

    def _topological_sort(self) -> List[ShotId]:
        """Kahn's algorithm with deterministic stable tie-break."""
        by_key = {
            str(s.shot_id): (str(s.scene_id), s.order, str(s.shot_id))
            for s in self.shots
        }
        key_of = {str(s.shot_id): s for s in self.shots}

        indegree: Dict[str, int] = {str(s.shot_id): 0 for s in self.shots}
        adjacency: Dict[str, List[str]] = {str(s.shot_id): [] for s in self.shots}
        for dep in self.dependencies:
            src, dst = str(dep.from_shot_id), str(dep.to_shot_id)
            if src not in indegree or dst not in indegree:
                continue
            adjacency[src].append(dst)
            indegree[dst] += 1

        ready = sorted(
            (n for n in indegree if indegree[n] == 0),
            key=lambda n: by_key[n],
        )
        order: List[ShotId] = []
        while ready:
            node = ready.pop(0)
            order.append(key_of[node].shot_id)
            for nxt in sorted(adjacency[node], key=lambda n: by_key[n]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
                    ready.sort(key=lambda n: by_key[n])
        return order


class CinematicPlan(BaseModel):
    """Shot plan for a revision: shots + typed dependency graph."""

    model_config = ConfigDict(frozen=True, extra="allow")

    plan_id: CinematicPlanId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    graph: ShotDependencyGraph = Field(default_factory=ShotDependencyGraph)
    locked: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Shot",
    "ShotDependency",
    "ShotDependencyGraph",
    "CinematicPlan",
]
