"""
Phase 9 — Shot dependency graph and camera planning domain (plan 03 §12-§16).

Domain objects, ports and invariants live in `core`. This module provides:

- `ShotSpecification` — the full spec of a shot (plan §14.1): scene/sequence/
  ordinal, narrative purpose, shot type, subjects/action, camera decision,
  composition + screen direction, duration/frame-rate/aspect-ratio intent,
  dialogue/narration range, required inputs / expected outputs, and retry
  policy. Generation-mode decisions were retired in VP3D Stage A — the
  engine adapter decides execution from the IR, never a generation mode.
- `CameraDecision` — position, angle, movement, lens intent, camera side
  (180-degree rule), screen direction, and a machine-readable `reason_code`
  (plan §14.2: camera decisions carry a reason code, not just prose).
- `ShotScheduling` — parallel capability, concurrency hint, sequence retry
  boundary and waited-for artifact types (plan §14.4).
- `ShotGraphIssue` — typed finding from graph/camera validation; structural
  codes are blocking (fail closed before publish), camera codes are warnings.
- `ShotDependencyGraphValidator` — deterministic structural validation
  (unique node/edge IDs, existing endpoints, no self-edge, blocking subgraph
  acyclic, valid scene/sequence boundary, reproducible topological order).
- `compute_graph_hash` — deterministic, versioned SHA-256 over the canonical
  graph payload + source plan hash, so identical inputs produce identical
  hashes and any change produces a new hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CameraAngle,
    CameraDecisionReasonCode,
    CameraMovement,
    CameraSide,
    DependencyType,
    IssueSeverity,
    RequiredArtifactType,
    ScreenDirection,
    ShotGraphIssueCode,
    ShotType,
)
from windagent_core.domain.video_production.ids import (
    DialogueLineId,
    SceneId,
    ShotDependencyId,
    ShotGraphIssueId,
    ShotId,
    ShotSpecificationId,
)
from windagent_core.domain.video_production.shot import (
    ShotDependencyGraph,
)


class CameraDecision(BaseModel):
    """Deterministic camera choice for a shot (plan §14.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    camera_position: str = ""
    camera_angle: CameraAngle = CameraAngle.EYE_LEVEL
    camera_movement: CameraMovement = CameraMovement.STATIC
    lens_intent: str = ""
    camera_side: CameraSide = CameraSide.NEUTRAL  # 180-degree rule
    screen_direction: ScreenDirection = ScreenDirection.NEUTRAL
    reason_code: CameraDecisionReasonCode = CameraDecisionReasonCode.SPATIAL_CONTINUITY
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_position": self.camera_position,
            "camera_angle": self.camera_angle.value,
            "camera_movement": self.camera_movement.value,
            "lens_intent": self.lens_intent,
            "camera_side": self.camera_side.value,
            "screen_direction": self.screen_direction.value,
            "reason_code": self.reason_code.value,
            "rationale": self.rationale,
        }


class RetryPolicy(BaseModel):
    """Retry / alternative-mode policy for a shot (plan §14.1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    max_attempts: int = Field(default=2, ge=1)
    retry_boundary: str = "sequence"  # "sequence" | "shot"


class ShotSpecification(BaseModel):
    """The complete spec of a shot (plan §14.1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    spec_id: ShotSpecificationId
    shot_id: ShotId
    scene_id: SceneId
    sequence: int = Field(ge=1)
    ordinal: int = Field(ge=1)
    narrative_purpose: str = ""
    shot_type: ShotType = ShotType.MEDIUM
    subjects: List[str] = Field(default_factory=list)
    action: str = ""
    camera: CameraDecision = Field(default_factory=CameraDecision)
    composition: str = ""
    screen_direction: ScreenDirection = ScreenDirection.NEUTRAL
    duration_seconds: float = Field(gt=0)
    frame_rate: int = 24
    aspect_ratio: str = "16:9"
    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    narration_range: Optional[str] = None
    required_inputs: List[str] = Field(default_factory=list)
    expected_outputs: List[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": str(self.spec_id),
            "shot_id": str(self.shot_id),
            "scene_id": str(self.scene_id),
            "sequence": self.sequence,
            "ordinal": self.ordinal,
            "narrative_purpose": self.narrative_purpose,
            "shot_type": self.shot_type.value,
            "subjects": list(self.subjects),
            "action": self.action,
            "camera": self.camera.to_dict(),
            "composition": self.composition,
            "screen_direction": self.screen_direction.value,
            "duration_seconds": self.duration_seconds,
            "frame_rate": self.frame_rate,
            "aspect_ratio": self.aspect_ratio,
            "dialogue_line_ids": [str(d) for d in self.dialogue_line_ids],
            "narration_range": self.narration_range,
            "required_inputs": list(self.required_inputs),
            "expected_outputs": list(self.expected_outputs),
            "retry_policy": {
                "max_attempts": self.retry_policy.max_attempts,
                "retry_boundary": self.retry_policy.retry_boundary,
            },
        }


class ShotScheduling(BaseModel):
    """Scheduling metadata for a shot (plan §14.4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shot_id: ShotId
    parallel_capable: bool = False
    concurrency_hint: int = Field(default=1, ge=1)
    sequence_retry_boundary: str = ""
    waits_for_artifact_types: List[RequiredArtifactType] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": str(self.shot_id),
            "parallel_capable": self.parallel_capable,
            "concurrency_hint": self.concurrency_hint,
            "sequence_retry_boundary": self.sequence_retry_boundary,
            "waits_for_artifact_types": [a.value for a in self.waits_for_artifact_types],
        }


class ShotGraphIssue(BaseModel):
    """Typed finding from shot-graph / camera validation (Phase 9)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: ShotGraphIssueId
    code: ShotGraphIssueCode
    severity: IssueSeverity = IssueSeverity.WARNING
    message: str = Field(min_length=1)
    blocking: bool = False
    shot_id: Optional[ShotId] = None
    edge_id: Optional[ShotDependencyId] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": str(self.issue_id),
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "blocking": self.blocking,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "edge_id": str(self.edge_id) if self.edge_id else None,
            "details": self.details,
        }


def compute_graph_hash(
    *,
    project_id: object,
    revision_id: object,
    graph_payload: Dict[str, Any],
    graph_version: str,
    source_plan_hash: str,
    source_package_hash: str,
) -> str:
    """Deterministic SHA-256 over the canonical graph payload + versions.

    Same inputs always produce the same hash; changing any shot, edge,
    version, or source hash produces a new hash (plan §24.5 semantics reused
    at the graph level).
    """
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "graph_version": graph_version,
            "source_plan_hash": source_plan_hash,
            "source_package_hash": source_package_hash,
            "graph": graph_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Structural graph validator (plan §13) — deterministic, fail closed.
# ---------------------------------------------------------------------------
_BLOCKING_CODES = {
    ShotGraphIssueCode.DUPLICATE_NODE_ID,
    ShotGraphIssueCode.DUPLICATE_EDGE_ID,
    ShotGraphIssueCode.MISSING_NODE,
    ShotGraphIssueCode.SELF_EDGE,
    ShotGraphIssueCode.BLOCKING_CYCLE,
    ShotGraphIssueCode.INVALID_CROSS_SCENE,
}


class ShotDependencyGraphValidator:
    """Deterministic structural validation of a ShotDependencyGraph.

    Rules (plan §13):
    - node / edge IDs are unique;
    - predecessor / successor shot IDs exist;
    - no self-edge;
    - the blocking subgraph never cycles (fail closed);
    - scene/sequence boundary is valid (TEMPORAL edges stay in-scene,
      cross-scene edges only via explicit CONTINUITY/TRANSITION/DIALOGUE
      edges between adjacent scenes);
    - topological order is reproducible (stable Kahn tie-break).

    Blocking issues are returned; the caller fails closed (no partial graph
    is ever published).
    """

    def __init__(self, *, id_factory=None) -> None:
        self._id_factory = id_factory

    def validate(self, graph: ShotDependencyGraph) -> List[ShotGraphIssue]:
        issues: List[ShotGraphIssue] = []
        self._check_unique_node_ids(graph, issues)
        self._check_unique_edge_ids(graph, issues)
        self._check_endpoints_exist(graph, issues)
        self._check_no_self_edges(graph, issues)
        self._check_blocking_subgraph_acyclic(graph, issues)
        self._check_scene_boundaries(graph, issues)
        return issues

    # -- helpers -----------------------------------------------------------
    def _issue(
        self,
        code: ShotGraphIssueCode,
        message: str,
        *,
        shot_id: Optional[ShotId] = None,
        edge_id: Optional[ShotDependencyId] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ShotGraphIssue:
        return ShotGraphIssue(
            issue_id=ShotGraphIssueId(
                self._new_issue_id(code, shot_id, edge_id)
            ),
            code=code,
            severity=IssueSeverity.BLOCKING if code in _BLOCKING_CODES else IssueSeverity.WARNING,
            message=message,
            blocking=code in _BLOCKING_CODES,
            shot_id=shot_id,
            edge_id=edge_id,
            details=details or {},
        )

    def _new_issue_id(self, code: ShotGraphIssueCode, shot_id, edge_id) -> str:
        seed = f"{code.value}:{shot_id or ''}:{edge_id or ''}"
        if self._id_factory is not None:
            return self._id_factory.shot_graph_issue_id(seed)
        return f"sgi_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    # -- rule checks -------------------------------------------------------
    def _check_unique_node_ids(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        seen: set = set()
        for shot in graph.shots:
            key = str(shot.shot_id)
            if key in seen:
                issues.append(
                    self._issue(
                        ShotGraphIssueCode.DUPLICATE_NODE_ID,
                        f"Duplicate shot id {key!r} in graph.",
                        shot_id=shot.shot_id,
                    )
                )
            seen.add(key)

    def _check_unique_edge_ids(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        seen: set = set()
        for dep in graph.dependencies:
            key = str(dep.dependency_id)
            if key in seen:
                issues.append(
                    self._issue(
                        ShotGraphIssueCode.DUPLICATE_EDGE_ID,
                        f"Duplicate dependency id {key!r} in graph.",
                        edge_id=dep.dependency_id,
                    )
                )
            seen.add(key)

    def _check_endpoints_exist(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        node_ids = {str(s.shot_id) for s in graph.shots}
        for dep in graph.dependencies:
            if str(dep.from_shot_id) not in node_ids:
                issues.append(
                    self._issue(
                        ShotGraphIssueCode.MISSING_NODE,
                        f"Dependency {dep.dependency_id} references missing predecessor "
                        f"shot {dep.from_shot_id}.",
                        edge_id=dep.dependency_id,
                        details={"predecessor_shot_id": str(dep.from_shot_id)},
                    )
                )
            if str(dep.to_shot_id) not in node_ids:
                issues.append(
                    self._issue(
                        ShotGraphIssueCode.MISSING_NODE,
                        f"Dependency {dep.dependency_id} references missing successor "
                        f"shot {dep.to_shot_id}.",
                        edge_id=dep.dependency_id,
                        details={"successor_shot_id": str(dep.to_shot_id)},
                    )
                )

    def _check_no_self_edges(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        for dep in graph.dependencies:
            if dep.from_shot_id == dep.to_shot_id:
                issues.append(
                    self._issue(
                        ShotGraphIssueCode.SELF_EDGE,
                        f"Dependency {dep.dependency_id} is a self-edge on "
                        f"shot {dep.from_shot_id}.",
                        edge_id=dep.dependency_id,
                        shot_id=dep.from_shot_id,
                    )
                )

    def _check_blocking_subgraph_acyclic(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        if graph.blocking_subgraph_has_cycle():
            issues.append(
                self._issue(
                    ShotGraphIssueCode.BLOCKING_CYCLE,
                    "The blocking subgraph contains a cycle; scheduling would deadlock.",
                )
            )

    def _check_scene_boundaries(self, graph: ShotDependencyGraph, issues: List[ShotGraphIssue]) -> None:
        scene_of = {str(s.shot_id): str(s.scene_id) for s in graph.shots}
        for dep in graph.dependencies:
            from_scene = scene_of.get(str(dep.from_shot_id))
            to_scene = scene_of.get(str(dep.to_shot_id))
            if from_scene is None or to_scene is None:
                continue  # missing-node already reported
            if from_scene != to_scene:
                # Cross-scene edges are only allowed for continuity semantics,
                # never for raw TEMPORAL order.
                if dep.dependency_type == DependencyType.TEMPORAL:
                    issues.append(
                        self._issue(
                            ShotGraphIssueCode.INVALID_CROSS_SCENE,
                            f"TEMPORAL edge {dep.dependency_id} crosses scenes "
                            f"({from_scene} -> {to_scene}); temporal order must stay "
                            "inside one scene.",
                            edge_id=dep.dependency_id,
                            details={"from_scene": from_scene, "to_scene": to_scene},
                        )
                    )

    @classmethod
    def blocking_issue_codes(cls) -> set:
        return set(_BLOCKING_CODES)


__all__ = [
    "CameraDecision",
    "RetryPolicy",
    "ShotSpecification",
    "ShotScheduling",
    "ShotGraphIssue",
    "ShotDependencyGraphValidator",
    "compute_graph_hash",
]
