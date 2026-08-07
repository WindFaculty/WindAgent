"""
Deterministic plan validator (plan §9.4).

The LLM only PROPOSES a structured plan (`PlannerOutput`); this validator
decides whether the proposal is valid. Rules:

- unknown scene / character / dialogue / reference IDs fail closed
  (unknown entity or reference makes validation FAIL — never silently drop);
- every scene must have at least one shot (shot count >= scene count);
- every dialogue line must be bound to exactly one shot (never silently cut);
- shot ordering must be deterministic (stable sort by scene order, shot order);
- total duration must be within the production constraint (or an issue);
- dialogue that does not fit its shot raises a DIALOGUE_DURATION_MISMATCH
  issue — the dialogue is NOT cut.

Validator failures raise `ValidationFailureError` (typed failure, no partial
plan); soft findings become `DirectorialIssue` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from windagent_core.domain.video_production.director import (
    DirectorialIssue,
    SceneObjective,
)
from windagent_core.domain.video_production.enums import (
    DirectorialIssueCategory,
    IssueSeverity,
)
from windagent_core.domain.video_production.ids import (
    ShotDependencyId,
    ShotId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.shot import (
    CinematicPlan,
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)

from windagent_intelligence.video.director.duration import DurationBudgetPolicy
from windagent_intelligence.video.director.models import (
    PlannerOutput,
    SceneObjectivePlan,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory


@dataclass(frozen=True)
class ValidationResult:
    """Validated plan pieces; `issues` holds soft (non-fatal) findings."""

    plan: CinematicPlan
    scene_objectives: List[SceneObjective]
    issues: List[DirectorialIssue] = field(default_factory=list)


class DirectorPlanValidator:
    """Deterministic validator: planner proposal -> canonical CinematicPlan."""

    def __init__(
        self,
        *,
        id_factory: StableIdFactory,
        duration_policy: DurationBudgetPolicy,
    ) -> None:
        self.id_factory = id_factory
        self.duration_policy = duration_policy

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def validate(self, package: VideoProductionPackage, output: PlannerOutput) -> ValidationResult:
        """Validate a planner proposal against the package.

        Raises `ValidationFailureError` on unknown/structural failures; soft
        findings (duration overflow, dialogue mismatch) are returned as issues.
        """
        self._fail_on_unknown_references(package, output)
        self._fail_on_missing_coverage(package, output)
        issues: List[DirectorialIssue] = []

        scenes = package.screenplay.scenes if package.screenplay else []
        objectives_by_scene: Dict[str, SceneObjectivePlan] = {
            str(o.scene_id): o for o in output.scene_objectives
        }

        # --- Build canonical shots in deterministic order -----------------
        shots: List[Shot] = []
        for scene in sorted(scenes, key=lambda s: (s.order, str(s.scene_id))):
            scene_id = scene.scene_id
            plan_shots = [p for p in output.shots if str(p.scene_id) == str(scene_id)]
            for shot_plan in sorted(plan_shots, key=lambda p: (p.order, str(p.scene_id))):
                shot_id = ShotId(self.id_factory.shot_id(str(scene_id), shot_plan.order))
                shots.append(
                    Shot(
                        shot_id=shot_id,
                        scene_id=scene_id,
                        order=shot_plan.order,
                        shot_type=shot_plan.shot_type,
                        camera_movement=shot_plan.camera_movement,
                        duration_seconds=shot_plan.duration_seconds,
                        framing_description=shot_plan.framing_description,
                        transition_type=shot_plan.transition_type,
                        dialogue_line_ids=list(shot_plan.dialogue_line_ids),
                        reference_asset_ids=list(shot_plan.reference_asset_ids),
                        metadata={
                            "camera_angle": shot_plan.camera_angle,
                            "narrative_purpose": shot_plan.narrative_purpose,
                        },
                    )
                )

        # --- Duration budget ---------------------------------------------
        total = self.duration_policy.total_timeline_seconds(shots)
        target = (
            package.creative_brief.target_duration_seconds
            if package.creative_brief
            else 0
        )
        if target > 0 and not self.duration_policy.in_budget(total, target):
            issues.append(
                DirectorialIssue(
                    issue_id=self._new_issue_id("duration", total),
                    category=DirectorialIssueCategory.DURATION_OVERFLOW,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Total timeline {total:.2f}s is outside the production "
                        f"constraint target {target}s ± "
                        f"{self.duration_policy.total_tolerance:.0%}."
                    ),
                    blocking=True,
                    details={
                        "total_seconds": total,
                        "target_seconds": target,
                        "policy_version": self.duration_policy.version,
                    },
                )
            )

        # --- Dialogue must fit its shot (never silently cut) ---------------
        dialogue_by_id = {str(d.dialogue_id): d for d in package.dialogue}
        for shot in shots:
            dialogue_seconds = sum(
                self.duration_policy.dialogue_duration(dialogue_by_id[str(line_id)].text)
                for line_id in shot.dialogue_line_ids
                if str(line_id) in dialogue_by_id
            )
            if dialogue_seconds > shot.duration_seconds:
                issues.append(
                    DirectorialIssue(
                        issue_id=self._new_issue_id("dialogue", str(shot.shot_id)),
                        category=DirectorialIssueCategory.DIALOGUE_DURATION_MISMATCH,
                        severity=IssueSeverity.BLOCKING,
                        message=(
                            f"Dialogue in shot {shot.shot_id} needs ~{dialogue_seconds:.2f}s "
                            f"but the shot is only {shot.duration_seconds:.2f}s. "
                            "Dialogue is NOT cut."
                        ),
                        blocking=True,
                        scene_id=shot.scene_id,
                        shot_id=shot.shot_id,
                        details={
                            "dialogue_seconds": round(dialogue_seconds, 3),
                            "shot_duration_seconds": shot.duration_seconds,
                            "policy_version": self.duration_policy.version,
                        },
                    )
                )

        # --- Scene objectives ---------------------------------------------
        scene_objectives: List[SceneObjective] = []
        for scene in sorted(scenes, key=lambda s: (s.order, str(s.scene_id))):
            proposed = objectives_by_scene.get(str(scene.scene_id))
            scene_objectives.append(
                SceneObjective(
                    scene_id=scene.scene_id,
                    objective=proposed.objective if proposed else "",
                    beats=[
                        {"beat_order": b.beat_order, "objective": b.objective, "source": b.source}
                        for b in (proposed.beats if proposed else [])
                    ],
                    required_story_facts=list(proposed.required_story_facts if proposed else []),
                )
            )

        # --- Temporal dependency edges (in-scene order) --------------------
        dependencies: List[ShotDependency] = []
        by_scene: Dict[str, List[Shot]] = {}
        for shot in shots:
            by_scene.setdefault(str(shot.scene_id), []).append(shot)
        for scene_shots in by_scene.values():
            ordered = sorted(scene_shots, key=lambda s: s.order)
            for prev, curr in zip(ordered, ordered[1:]):
                dep_id = f"dep_{self.id_factory.entity_id('sht', f'{prev.shot_id}:{curr.shot_id}')}"
                dependencies.append(
                    ShotDependency(
                        dependency_id=ShotDependencyId(dep_id),
                        from_shot_id=prev.shot_id,
                        to_shot_id=curr.shot_id,
                        dependency_type="TEMPORAL",
                        reason="in-scene shot order",
                    )
                )

        plan = CinematicPlan(
            plan_id=self.id_factory.cinematic_plan_id(
                str(package.project_id), str(package.revision_id)
            ),
            project_id=package.project_id,
            revision_id=package.revision_id,
            graph=ShotDependencyGraph(shots=shots, dependencies=dependencies),
            locked=False,
        )
        return ValidationResult(plan=plan, scene_objectives=scene_objectives, issues=issues)

    # ------------------------------------------------------------------
    # Fail-closed rules
    # ------------------------------------------------------------------
    def _fail_on_unknown_references(self, package: VideoProductionPackage, output: PlannerOutput) -> None:
        """Unknown entity/reference IDs make the plan INVALID (plan §9.4).

        The package itself is already validated by the canonical
        `VideoProductionPackageValidator` in the service; here we only check
        the PLANNER OUTPUT against the package's known IDs.
        """
        scene_ids = {str(s) for s in (package.screenplay.scene_ids if package.screenplay else [])}
        asset_ids = {str(a.asset_id) for a in package.assets}
        dialogue_ids = {str(d.dialogue_id) for d in package.dialogue}

        unknown: List[str] = []
        for obj in output.scene_objectives:
            if str(obj.scene_id) not in scene_ids:
                unknown.append(f"planner objective references unknown scene {obj.scene_id}")
        for shot in output.shots:
            if str(shot.scene_id) not in scene_ids:
                unknown.append(f"planner shot references unknown scene {shot.scene_id}")
            for did in shot.dialogue_line_ids:
                if str(did) not in dialogue_ids:
                    unknown.append(f"planner shot references unknown dialogue {did}")
            for aid in shot.reference_asset_ids:
                if str(aid) not in asset_ids:
                    unknown.append(f"planner shot references unknown asset {aid}")

        if unknown:
            raise ValidationFailureError(
                "Planner output contains unknown entity/reference IDs.",
                details={"unknown": sorted(set(unknown))},
            )

    def _fail_on_missing_coverage(self, package: VideoProductionPackage, output: PlannerOutput) -> None:
        """Every scene needs >= 1 shot and every dialogue line must be bound."""
        scenes = package.screenplay.scenes if package.screenplay else []
        for scene in scenes:
            if not any(str(p.scene_id) == str(scene.scene_id) for p in output.shots):
                raise ValidationFailureError(
                    f"Scene {scene.scene_id} has no planned shot.",
                    details={"scene_id": str(scene.scene_id)},
                )
        bound = {
            str(did)
            for p in output.shots
            for did in p.dialogue_line_ids
        }
        for d in package.dialogue:
            if str(d.dialogue_id) not in bound:
                raise ValidationFailureError(
                    f"Dialogue line {d.dialogue_id} is not bound to any shot "
                    "(silently cutting dialogue is forbidden).",
                    details={"dialogue_id": str(d.dialogue_id)},
                )

    def _new_issue_id(self, kind: str, seed: object) -> str:
        return self.id_factory.directorial_issue_id(f"{kind}:{seed}")


__all__ = ["DirectorPlanValidator", "ValidationResult"]
