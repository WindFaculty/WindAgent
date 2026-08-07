"""
ShotGraphPlannerService (Phase 9) — enriches a Phase 8 CinematicPlan into a
full shot dependency graph with camera planning and scheduling metadata.

Responsibilities (plan 03 §12-§16):
- build a typed `ShotDependencyGraph` (TEMPORAL / DIALOGUE / CONTINUITY /
  TRANSITION / VISUAL_REFERENCE / ASSET edges) from the plan shots;
- decide camera per shot deterministically with machine-readable reason
  codes (plan §14.2). Generation-mode decisions were retired in VP3D Stage A
  — the engine adapter decides execution from the IR, never a mode;
- compute scheduling metadata (independent shots, concurrency hints,
  sequence retry boundaries) — orchestration keeps final authority;
- validate the graph BEFORE publishing: structural defects (duplicate IDs,
  missing nodes, self-edges, blocking cycles, invalid cross-scene edges)
  FAIL CLOSED — no partial/invalid graph is ever emitted;
- record a deterministic, versioned graph hash tied to the source plan.

The service is fully deterministic and never calls a provider: the LLM
proposed the shot plan in Phase 8; this layer only applies rules.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from windagent_core.domain.video_production.ids import (
    ReferenceAssetId,
    ShotSpecificationId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.shot import (
    CinematicPlan,
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)
from windagent_core.domain.video_production.shot_graph import (
    RetryPolicy,
    ShotDependencyGraphValidator,
    ShotSpecification,
    compute_graph_hash,
)
from windagent_core.domain.video_production.validation import (
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.shot_planner.camera import CameraPlanner
from windagent_intelligence.video.shot_planner.graph import ShotGraphBuilder
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt
from windagent_intelligence.video.shot_planner.scheduling import ShotScheduler


class ShotGraphPlannerService:
    """Deterministic shot graph + camera planning over a CinematicPlan."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        camera_planner: Optional[CameraPlanner] = None,
        graph_builder: Optional[ShotGraphBuilder] = None,
        scheduler: Optional[ShotScheduler] = None,
        validator: Optional[ShotDependencyGraphValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.camera_planner = camera_planner or CameraPlanner(
            id_factory=self.id_factory,
        )
        self.graph_builder = graph_builder or ShotGraphBuilder(
            id_factory=self.id_factory,
        )
        self.scheduler = scheduler or ShotScheduler()
        self.validator = validator or ShotDependencyGraphValidator(
            id_factory=self.id_factory,
        )

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def plan(
        self,
        package: VideoProductionPackage,
        plan: CinematicPlan,
        *,
        production_max_parallel: Optional[int] = None,
        require_locked: bool = True,
    ) -> ShotGraphReceipt:
        """Build the typed graph + camera/scheduling decisions.

        Raises `ValidationFailureError` on structural graph defects (fail
        closed — a broken graph is never published). Camera warnings are
        returned as non-blocking issues on the receipt.
        """
        package_issues = VideoProductionPackageValidator.validate(package)
        if package_issues:
            raise ValidationFailureError(
                "Cannot build a shot graph from an invalid package.",
                details={
                    "issue_count": len(package_issues),
                    "first": [i.code for i in package_issues[:5]],
                },
            )
        if plan is None or not plan.graph.shots:
            raise ValidationFailureError(
                "Shot graph planning requires a plan with at least one shot.",
            )
        if require_locked and not plan.locked:
            raise ValidationFailureError(
                "Shot graph planning requires a LOCKED shot plan "
                "(plan.locked=False).",
                details={"locked": bool(plan.locked)},
            )

        # 1. Typed dependency graph.
        graph = self.graph_builder.build(package, list(plan.graph.shots))

        # 2. Deterministic camera decisions per shot.
        specs = self._build_specifications(package, plan, graph)

        # 3. Scheduling metadata (independent shots, hints, boundaries).
        production_max_parallel = _production_constraint_max_parallel(package)
        scheduling = self.scheduler.schedule(
            graph,
            production_max_parallel=production_max_parallel,
        )

        # 4. Camera rule warnings (never block publish).
        camera_by_shot = {str(s.shot_id): s.camera for s in specs}
        shots_by_scene = _group_shots_by_scene(graph.shots)
        camera_issues = self.camera_planner.validate(
            shots_by_scene=shots_by_scene,
            camera_by_shot=camera_by_shot,
        )

        # 5. Structural graph validation — FAIL CLOSED.
        structural = self.validator.validate(graph)
        blocking = [i for i in structural if i.blocking]
        if blocking:
            raise ValidationFailureError(
                "Shot graph failed structural validation; no graph is published.",
                details={
                    "blocking_issue_count": len(blocking),
                    "first": [i.code.value for i in blocking[:5]],
                },
            )

        # 6. Deterministic graph hash.
        source_package_hash = package.content_hash()
        graph_hash = compute_graph_hash(
            project_id=package.project_id,
            revision_id=package.revision_id,
            graph_payload=json.loads(graph.model_dump_json()),
            graph_version=self._graph_version(),
            source_plan_hash=_plan_hash(plan),
            source_package_hash=source_package_hash,
        )

        return ShotGraphReceipt(
            graph=graph,
            specifications=specs,
            scheduling=scheduling,
            issues=[*structural, *camera_issues],
            graph_hash=graph_hash,
            source_plan_hash=_plan_hash(plan),
            source_package_hash=source_package_hash,
            graph_version=self._graph_version(),
            camera_rule_version=self.camera_planner.rule_version,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_specifications(
        self,
        package: VideoProductionPackage,
        plan: CinematicPlan,
        graph: ShotDependencyGraph,
    ) -> List[ShotSpecification]:
        scenes_by_id = (
            {str(s.scene_id): s for s in package.screenplay.scenes}
            if package.screenplay
            else {}
        )
        incoming_by_shot: Dict[str, List[ShotDependency]] = {}
        for dep in graph.dependencies:
            incoming_by_shot.setdefault(str(dep.to_shot_id), []).append(dep)

        aspect_ratio = (
            package.creative_brief.aspect_ratio
            if package.creative_brief and package.creative_brief.aspect_ratio
            else "16:9"
        )

        specs: List[ShotSpecification] = []
        for shot in sorted(
            graph.shots, key=lambda s: (str(s.scene_id), s.order)
        ):
            scene = scenes_by_id.get(str(shot.scene_id))
            camera = self.camera_planner.decide(shot)
            subjects = _shot_subjects(shot, package)
            required_inputs = [
                f"dialogue:{d}" for d in shot.dialogue_line_ids
            ] + [f"asset:{a}" for a in shot.reference_asset_ids]
            expected_outputs = ["shot_clip", "tail_frame"]
            specs.append(
                ShotSpecification(
                    spec_id=ShotSpecificationId(
                        self.id_factory.shot_spec_id(str(shot.shot_id))
                    ),
                    shot_id=shot.shot_id,
                    scene_id=shot.scene_id,
                    sequence=_scene_order(scene) if scene else 1,
                    ordinal=shot.order,
                    narrative_purpose=shot.metadata.get("narrative_purpose", ""),
                    shot_type=shot.shot_type,
                    subjects=subjects,
                    action=shot.framing_description,
                    camera=camera,
                    composition=shot.framing_description,
                    screen_direction=camera.screen_direction,
                    duration_seconds=shot.duration_seconds,
                    frame_rate=24,
                    aspect_ratio=aspect_ratio,
                    dialogue_line_ids=list(shot.dialogue_line_ids),
                    narration_range=None,
                    required_inputs=required_inputs,
                    expected_outputs=expected_outputs,
                    retry_policy=RetryPolicy(
                        max_attempts=2,
                        retry_boundary="sequence",
                    ),
                )
            )
        return specs

    def _graph_version(self) -> str:
        return "1.0.0"


def _production_constraint_max_parallel(
    package: VideoProductionPackage,
) -> Optional[int]:
    if package.creative_brief is None:
        return None
    raw = package.creative_brief.production_constraints or {}
    value = raw.get("max_parallel_shots")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _plan_hash(plan: CinematicPlan) -> str:
    return str(plan.metadata.get("plan_hash", ""))


def _group_shots_by_scene(shots: List[Shot]) -> Dict[str, List[Shot]]:
    by_scene: Dict[str, List[Shot]] = {}
    for shot in shots:
        by_scene.setdefault(str(shot.scene_id), []).append(shot)
    return by_scene


def _scene_character_asset_map(
    package: VideoProductionPackage,
) -> Dict[str, List[ReferenceAssetId]]:
    mapping: Dict[str, List[ReferenceAssetId]] = {}
    for char in package.characters:
        for scene in (package.screenplay.scenes if package.screenplay else []):
            if str(char.character_id) in {str(c) for c in scene.character_ids}:
                mapping.setdefault(str(scene.scene_id), []).extend(
                    char.portrait_asset_ids
                )
    return mapping


def _scene_location_asset_map(
    package: VideoProductionPackage,
) -> Dict[str, List[ReferenceAssetId]]:
    mapping: Dict[str, List[ReferenceAssetId]] = {}
    location_by_id = {str(loc.location_id): loc for loc in package.locations}
    for scene in (package.screenplay.scenes if package.screenplay else []):
        loc = location_by_id.get(str(scene.location_id))
        if loc:
            mapping.setdefault(str(scene.scene_id), []).extend(loc.reference_asset_ids)
    return mapping


def _shot_subjects(shot: Shot, package: VideoProductionPackage) -> List[str]:
    subjects = [str(a) for a in shot.reference_asset_ids]
    dialogue_by_id = {str(d.dialogue_id): d for d in package.dialogue}
    for line_id in shot.dialogue_line_ids:
        line = dialogue_by_id.get(str(line_id))
        if line:
            subjects.append(str(line.character_id))
    return list(dict.fromkeys(subjects))


def _scene_order(scene) -> int:
    order = getattr(scene, "order", 1)
    return int(order) if order else 1


__all__ = ["ShotGraphPlannerService"]
