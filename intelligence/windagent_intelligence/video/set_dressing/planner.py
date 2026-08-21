"""
SetDressingPlanner (VP3D Phase 12) — orchestrates environment + prop +
character placement + spatial validation into a single deterministic
`SetDressingPlan`, and computes scoped invalidation.

Components compose:
- EnvironmentBuilder      — IR env + approved asset -> EnvironmentSpec.
- PropPlacementPlanner     — approved props onto anchors (seeded scatter).
- SpatialConstraintValidator — proxy-bounds spatial findings (fail closed).

Camera and light remain typed PLACEHOLDERS here (plan Stage F §4 item 5);
Stage G compiles the full rig from the shot graph.

Incremental compile (plan Stage F §3 item 7 / §4 item 3): the plan carries an
idempotency key derived from its input+tool hash. A changed prop revision hash
changes the key and thus invalidates only the dependent scene/shot — the
`SetDressingPlannerReceipt.invalidated_scene_ids` surfaces exactly which
scenes are stale. Unchanged scenes keep their key and their previously
compiled artifact.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from windagent_core.domain.video_production.set_dressing import (
    CameraPlaceholder,
    CharacterPlacement,
    EnvironmentSpec,
    LightPlaceholder,
    SetDressingPlan,
    SpatialValidationReport,
    Vec3,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.set_dressing.environment_builder import (
    EnvironmentBuilder,
)
from windagent_intelligence.video.set_dressing.prop_planner import (
    ApprovedProp,
    PropPlacementPlanner,
)
from windagent_intelligence.video.set_dressing.spatial_validator import (
    SpatialConstraintValidator,
)

DEFAULT_CAMERA_PLACEHOLDER = {
    "name": "cam_placeholder",
    "position": {"x": 5.0, "y": -5.0, "z": 2.0},
    "look_at": {"x": 0.0, "y": 0.0, "z": 1.0},
}
DEFAULT_LIGHT_PLACEHOLDERS = [
    {"name": "key_placeholder", "kind": "AREA",
     "position": {"x": 3.0, "y": -3.0, "z": 4.0}},
]


class SetDressingPlanner:
    """Deterministic set-dressing orchestrator for one IR scene."""

    planner_version = "1.0.0"

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        environment_builder: Optional[EnvironmentBuilder] = None,
        prop_planner: Optional[PropPlacementPlanner] = None,
        validator: Optional[SpatialConstraintValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.environment_builder = environment_builder or EnvironmentBuilder(
            id_factory=self.id_factory
        )
        self.prop_planner = prop_planner or PropPlacementPlanner(
            id_factory=self.id_factory
        )
        self.validator = validator or SpatialConstraintValidator(
            id_factory=self.id_factory
        )

    # ------------------------------------------------------------------
    def plan(
        self,
        *,
        scene_id,
        environment_spec: EnvironmentSpec,
        approved_props: Dict[str, ApprovedProp],
        props=None,
        characters: Optional[List[CharacterPlacement]] = None,
        cameras: Optional[List[CameraPlaceholder]] = None,
        lights: Optional[List[LightPlaceholder]] = None,
        seed: int = 0,
        scatter_policy: str = "anchor",
        require_clean: bool = True,
        tool_hash: str = "",
        prior_key: Optional[str] = None,
    ) -> "SetDressingPlanReceipt":
        """Compose a set-dressing plan + validate + compute invalidation scope.

        ``props`` is a list of IR PropInstance; each must have an ApprovedProp
        in ``approved_props`` keyed by instance id or prop id. Characters
        arrive pre-placed (their placement is resolved by a separate
        character-placement step that checks foot contact/reachability — Stage
        D character anchors feed this).
        """
        prop_findings: List = []
        placements = self.prop_planner.place(
            props or [],
            approved = approved_props,
            env=environment_spec,
            seed=seed,
            scatter_policy=scatter_policy,
            findings_out=prop_findings,
        )

        plan = SetDressingPlan(
            plan_id=self.id_factory.set_dressing_plan_id(str(scene_id)),
            scene_id=str(scene_id),
            seed=seed,
            compiler_version=(
                f"{self.planner_version}/{self.environment_builder.builder_version}/"
                f"{self.prop_planner.SCATTER_ALGORITHM_VERSION if hasattr(self.prop_planner, 'SCATTER_ALGORITHM_VERSION') else '1.0.0'}"
            ),
            environment=environment_spec,
            props=placements,
            characters=characters or [],
            cameras=cameras or _default_cameras(),
            lights=lights or _default_lights(),
            input_hash=self._input_hash(scene_id, environment_spec, approved_props),
            tool_hash=tool_hash,
        )

        report = self.validator.validate(plan)
        blocking_set = report.blocking_findings or [f for f in prop_findings if f.blocking]
        combined_ok = (not blocking_set)
        if require_clean and not combined_ok:
            raise ValidationFailureError(
                "Set-dressing plan failed spatial validation; no plan is published.",
                details={
                    "scene_id": str(scene_id),
                    "blocking_count": len(blocking_set),
                    "kinds": sorted({f.kind for f in blocking_set}),
                },
            )

        receipt = SetDressingPlanReceipt(
            plan=plan,
            validation=report,
            prop_placement_findings=list(prop_findings),
            invalidated_scene_ids=self._invalidation_scope(plan, prior_key),
            cleaned_ok=combined_ok,
        )
        return receipt

    # ------------------------------------------------------------------
    def _input_hash(
        self,
        scene_id,
        env: EnvironmentSpec,
        approved_props: Dict[str, ApprovedProp],
    ) -> str:
        env_payload = json.loads(env.model_dump_json())
        prop_hashes = sorted(
            (str(k), v.revision_hash) for k, v in approved_props.items()
        )
        canonical = json.dumps(
            [str(scene_id), env_payload, prop_hashes],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _invalidation_scope(
        self, plan: SetDressingPlan, prior_key: Optional[str]
    ) -> List[str]:
        """Scenes whose prior artifact is stale and must be rebuilt.

        Incremental compile (plan Stage F §3 item 7): when the durable
        `prior_key` equals the current plan's idempotency key, the inputs are
        unchanged and the prior `.blend` is REUSED (nothing invalidated). When
        the key changed — e.g. one prop's approved revision hash changed — the
        owning scene is invalidated (its artifact must be rebuilt); unchanged
        scenes keep their key and are reused. Only the changed scene/shot is
        rebuilt, never the whole shot graph.
        """
        current_key = plan.idempotency_key()
        if prior_key is not None and prior_key == current_key:
            return []
        return [plan.scene_id]

    @staticmethod
    def previous_key(plan: SetDressingPlan) -> str:
        """The durable key consumers reuse to detect change."""
        return plan.idempotency_key()


class SetDressingPlanReceipt:
    """Result of composition: the plan + validation + invalidation scope."""

    def __init__(
        self,
        *,
        plan: SetDressingPlan,
        validation: SpatialValidationReport,
        prop_placement_findings: Optional[List] = None,
        invalidated_scene_ids: Optional[List[str]] = None,
        cleaned_ok: bool = True,
    ) -> None:
        self.plan = plan
        self.validation = validation
        self.prop_placement_findings = prop_placement_findings or []
        self.invalidated_scene_ids = invalidated_scene_ids or []
        self.cleaned_ok = cleaned_ok

    @property
    def plan_hash(self) -> str:
        return self.plan.plan_hash()

    @property
    def ok(self) -> bool:
        return self.cleaned_ok


def _default_cameras() -> List[CameraPlaceholder]:
    c = DEFAULT_CAMERA_PLACEHOLDER
    return [CameraPlaceholder(
        name=c["name"],
        position=Vec3(**c["position"]),
        look_at=Vec3(**c["look_at"]),
    )]


def _default_lights() -> List[LightPlaceholder]:
    return [
        LightPlaceholder(name=spec["name"], kind=spec["kind"],
                         position=Vec3(**spec["position"]))
        for spec in DEFAULT_LIGHT_PLACEHOLDERS
    ]


__all__ = ["SetDressingPlanner", "SetDressingPlanReceipt"]
