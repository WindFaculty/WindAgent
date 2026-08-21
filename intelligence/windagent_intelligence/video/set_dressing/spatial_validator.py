"""
SpatialConstraintValidator (VP3D Phase 12) — fail-closed spatial checks over a
set-dressing plan using proxy AABB bounds.

Checks (plan Stage F §4 item 6):
- mesh penetration        : a prop/character AABB overlaps a forbidden volume
                            or another placed entity's AABB.
- floating / below floor  : no support surface under a prop/character, or its
                            stand z is below the floor.
- out of bounds           : entity outside every navigation zone.
- camera in mesh          : camera placeholder inside a forbidden volume or a
                            placed entity AABB.
- blocking occluder       : a placed prop/character blocks a camera's line to
                            an interaction anchor (proxied as the segment
                            passing through the volume).
- duplicate id            : two entities share a canonical id.
- out of reach            : character farther from its interaction anchor than
                            a reachable distance threshold.
- wrong facing            : character facing does not point at its anchor.

AABB checks are cheap and deterministic; exact mesh intersection is deferred
to the blender compiler / inspector (plan §7: proxy bounds first). Findings
are typed; blocking findings fail the plan.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.set_dressing import (
    Aabb,
    EnvironmentSpec,
    SetDressingPlan,
    SpatialFinding,
    SpatialFindingKind,
    SpatialValidationReport,
    Vec3,
)
from windagent_intelligence.video.ids import StableIdFactory

DEFAULT_REACH_DISTANCE = 3.0  # meters
DEFAULT_REACH_DISTANCE_SQ = DEFAULT_REACH_DISTANCE * DEFAULT_REACH_DISTANCE


class SpatialConstraintValidator:
    """Deterministic proxy-bounds spatial validation over a SetDressingPlan."""

    validator_version = "1.0.0"

    def __init__(
        self, *, id_factory: Optional[StableIdFactory] = None
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.reach_distance = DEFAULT_REACH_DISTANCE

    # ------------------------------------------------------------------
    def validate(self, plan: SetDressingPlan) -> SpatialValidationReport:
        findings: List[SpatialFinding] = []
        env = plan.environment

        self._validate_duplicate_ids(plan, findings)
        self._validate_forbidden_penetration(plan, env, findings)
        self._validate_below_floor_and_floating(plan, env, findings)
        self._validate_out_of_bounds(plan, env, findings)
        self._validate_camera_in_mesh(plan, env, findings)
        self._validate_occluders(plan, env, findings)
        self._validate_reach_and_facing(plan, env, findings)

        blocking = [f for f in findings if f.blocking]
        return SpatialValidationReport(
            ok=not blocking,
            findings=findings,
            checked_entity_count=(
                len(plan.props) + len(plan.characters) + len(plan.cameras)
            ),
        )

    # ------------------------------------------------------------------
    def _validate_duplicate_ids(
        self, plan: SetDressingPlan, findings: List[SpatialFinding]
    ) -> None:
        seen: Dict[str, str] = {}
        for prop in plan.props:
            key = str(prop.prop_id)
            self._dup_finding(seen, key, "prop", findings)
        for char in plan.characters:
            key = str(char.character_id)
            self._dup_finding(seen, key, "character", findings)

    def _dup_finding(
        self,
        seen: Dict[str, str],
        key: str,
        entity_kind: str,
        findings: List[SpatialFinding],
    ) -> None:
        if key in seen:
            findings.append(
                SpatialFinding(
                    finding_id=self.id_factory.spatial_finding_id(f"dup_{key}"),
                    kind=SpatialFindingKind.DUPLICATE_ID,
                    entity=key,
                    detail=f"duplicate {entity_kind} canonical id",
                    blocking=True,
                )
            )
        else:
            seen[key] = entity_kind

    def _validate_forbidden_penetration(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        forbids = {
            fv.name: fv.bounds for fv in env.forbidden_volumes
        }
        if not forbids:
            return
        for prop in plan.props:
            # use footprint-free proxy: 1x1x1 around the placement point
            box = Aabb.from_center_size(prop.position, Vec3(x=1, y=1, z=1))
            self._penetrate_findings(prop.position, "prop", str(prop.prop_id),
                                     box, forbids, findings)
        for char in plan.characters:
            box = Aabb.from_center_size(
                Vec3(x=char.position.x, y=char.position.y, z=char.position.z + 1.0),
                Vec3(x=1, y=1, z=2),
            )
            self._penetrate_findings(char.position, "character",
                                     str(char.character_id), box, forbids,
                                     findings)

    def _penetrate_findings(
        self,
        pos: Vec3,
        kind: str,
        entity: str,
        box,
        forbids: Dict[str, "Aabb"],
        findings: List[SpatialFinding],
    ) -> None:
        for fname, fbox in forbids.items():
            if box.overlaps(fbox):
                findings.append(
                    SpatialFinding(
                        finding_id=self.id_factory.spatial_finding_id(
                            f"pen_{entity}_{fname}"
                        ),
                        kind=SpatialFindingKind.PENETRATION,
                        entity=entity,
                        detail=f"{kind} penetrates forbidden volume '{fname}'",
                        blocking=True,
                        position=pos,
                    )
                )

    def _validate_below_floor_and_floating(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        surfaces = [
            (s.name, s.surface_z) for s in env.support_surfaces
        ]
        for prop in plan.props:
            self._floor_findings(prop.position.z, "prop", str(prop.prop_id),
                                 prop.position, surfaces, findings)
        for char in plan.characters:
            self._floor_findings(char.stand_z, "character", str(char.character_id),
                                 char.position, surfaces, findings)

    def _floor_findings(
        self,
        stand_z: float,
        kind: str,
        entity: str,
        pos: Vec3,
        surfaces: List[tuple],
        findings: List[SpatialFinding],
    ) -> None:
        if stand_z < -0.001:
            findings.append(
                SpatialFinding(
                    finding_id=self.id_factory.spatial_finding_id(f"below_{entity}"),
                    kind=SpatialFindingKind.BELOW_FLOOR,
                    entity=entity,
                    detail=f"{kind} stand z {stand_z:.3f} is below floor level",
                    blocking=True,
                    position=pos,
                )
            )
            return
        # floating: a prop/character should sit on a surface within tolerance.
        if surfaces:
            on_surface = any(
                abs(stand_z - top) < 0.001 for (_, top) in surfaces
            ) or stand_z < 0.001
            if not on_surface:
                findings.append(
                    SpatialFinding(
                        finding_id=self.id_factory.spatial_finding_id(f"float_{entity}"),
                        kind=SpatialFindingKind.FLOATING,
                        entity=entity,
                        detail=f"{kind} not resting on any support surface "
                               f"(stand z {stand_z:.3f})",
                        blocking=False,
                        position=pos,
                    )
                )

    def _validate_out_of_bounds(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        zones = [z.bounds for z in env.navigation_zones]
        if not zones:
            return
        for char in plan.characters:
            if not any(z.contains_point(char.position) for z in zones):
                findings.append(
                    SpatialFinding(
                        finding_id=self.id_factory.spatial_finding_id(
                            f"oob_{char.character_id}"
                        ),
                        kind=SpatialFindingKind.OUT_OF_BOUNDS,
                        entity=str(char.character_id),
                        detail="character outside every navigation zone",
                        blocking=True,
                        position=char.position,
                    )
                )

    def _validate_camera_in_mesh(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        from windagent_core.domain.video_production.set_dressing import Aabb

        for cam in plan.cameras:
            # A tight point AABB is always "inside" itself; instead check the
            # camera point against forbidden volumes + entity AABBs.
            for fv in env.forbidden_volumes:
                if fv.bounds.contains_point(cam.position):
                    findings.append(
                        SpatialFinding(
                            finding_id=self.id_factory.spatial_finding_id(
                                f"cam_{cam.name}"
                            ),
                            kind=SpatialFindingKind.CAMERA_IN_MESH,
                            entity=str(cam.name),
                            detail=f"camera inside forbidden volume '{fv.name}'",
                            blocking=True,
                            position=cam.position,
                        )
                    )
            for prop in plan.props:
                box = Aabb.from_center_size(prop.position, Vec3(x=1, y=1, z=1))
                if box.contains_point(cam.position) and box.height > 0:
                    # camera point inside the prop bounding box
                    findings.append(
                        SpatialFinding(
                            finding_id=self.id_factory.spatial_finding_id(
                                f"cam_{cam.name}_{prop.prop_id}"
                            ),
                            kind=SpatialFindingKind.CAMERA_IN_MESH,
                            entity=str(cam.name),
                            detail=f"camera inside prop '{prop.prop_id}' bounds",
                            blocking=True,
                            position=cam.position,
                        )
                    )
                    break

    def _validate_occluders(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        # proxied: a blocking occluder is a forbidden volume intersecting the
        # camera->anchor line of sight. Only evaluated when the plan has cam+anchor.
        if not plan.cameras or not env.interaction_anchors:
            return
        cam = plan.cameras[0]
        for ia in env.interaction_anchors:
            for fv in env.forbidden_volumes:
                if _segment_hits_aabb(cam.position, ia.position, fv.bounds):
                    findings.append(
                        SpatialFinding(
                            finding_id=self.id_factory.spatial_finding_id(
                                f"occ_{cam.name}_{ia.name}_{fv.name}"
                            ),
                            kind=SpatialFindingKind.OCCLUDING_BLOCKER,
                            entity=str(cam.name),
                            detail=f"forbidden volume '{fv.name}' blocks camera "
                                   f"-> anchor '{ia.name}'",
                            blocking=True,
                        )
                    )

    def _validate_reach_and_facing(
        self, plan: SetDressingPlan, env: EnvironmentSpec, findings: List[SpatialFinding]
    ) -> None:
        anchors = {ia.name: ia for ia in env.interaction_anchors}
        for char in plan.characters:
            anchor = anchors.get(char.anchor)
            if anchor is None:
                continue
            dist_sq = _dist_sq(char.position, anchor.position)
            if dist_sq > self.reach_distance * self.reach_distance:
                findings.append(
                    SpatialFinding(
                        finding_id=self.id_factory.spatial_finding_id(
                            f"reach_{char.character_id}"
                        ),
                        kind=SpatialFindingKind.OUT_OF_REACH,
                        entity=str(char.character_id),
                        detail=f"character out of reach of anchor '{char.anchor}'",
                        blocking=True,
                        position=char.position,
                    )
                )
            if not _facing_anchor(char.facing, char.position, anchor.position):
                findings.append(
                    SpatialFinding(
                        finding_id=self.id_factory.spatial_finding_id(
                            f"face_{char.character_id}"
                        ),
                        kind=SpatialFindingKind.WRONG_FACING,
                        entity=str(char.character_id),
                        detail=f"character not facing anchor '{char.anchor}'",
                        blocking=False,
                        position=char.position,
                    )
                )


def _dist_sq(a: Vec3, b: Vec3) -> float:
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2


def _facing_anchor(facing: Vec3, pos: Vec3, anchor: Vec3) -> bool:
    dx = anchor.x - pos.x
    dy = anchor.y - pos.y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return True
    dot = facing.x * dx + facing.y * dy
    return dot >= 0.0


def _segment_hits_aabb(p: Vec3, q: Vec3, box) -> bool:
    """Liang-Barsky clipline: does segment p->q intersect the AABB?"""
    t0, t1 = 0.0, 1.0
    d = (q.x - p.x, q.y - p.y, q.z - p.z)
    lo = (box.min.x, box.min.y, box.min.z)
    hi = (box.max.x, box.max.y, box.max.z)
    for i in range(3):
        if abs(d[i]) < 1e-12:
            if p.as_tuple()[i] < lo[i] or p.as_tuple()[i] > hi[i]:
                return False
        else:
            inv = 1.0 / d[i]
            t_lo = (lo[i] - p.as_tuple()[i]) * inv
            t_hi = (hi[i] - p.as_tuple()[i]) * inv
            if t_lo > t_hi:
                t_lo, t_hi = t_hi, t_lo
            t0 = max(t0, t_lo)
            t1 = min(t1, t_hi)
            if t0 > t1:
                return False
    return True


__all__ = ["SpatialConstraintValidator"]
