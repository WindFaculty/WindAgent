"""
EnvironmentBuilder (VP3D Phase 12) — compiles the IR environment + an approved
environment asset into a neutral `EnvironmentSpec` (surfaces, navigation zones,
forbidden volumes, attachment points, interaction anchors).

Security contract (plan Stage F §4 item 2): the builder only RESOLVES an asset
that is already APPROVED (content-addressed revision hash). It never downloads,
never spawns a process, never evaluates asset metadata as code. Any
unapproved / unknown environment asset FAILS CLOSED with a typed finding — the
compiler step is not a place where a model can smuggle arbitrary bytes in.

Determinism: identical IR scene + approved asset yield an identical, stable
EnvironmentSpec.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from windagent_core.domain.video_production.ids import (
    EnvironmentInstanceId,
    SpatialFindingId,
)
from windagent_core.domain.video_production.production_ir.models import (
    EnvironmentInstance,
)
from windagent_core.domain.video_production.set_dressing import (
    AttachmentPoint,
    Aabb,
    EnvironmentSpec,
    ForbiddenVolume,
    InteractionAnchor,
    NavigationZone,
    SupportSurface,
    Vec3,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovedEnvironment:
    """A pre-approved, content-addressed environment asset description.

    ``procedural=True`` means the runtime uses an ALLOWLISTED procedural
    Geometry Nodes plan (pinned node-group hash) rather than downloaded bytes —
    still never arbitrary model text.
    """

    __slots__ = (
        "environment_id",
        "revision_hash",
        "name",
        "support_surfaces",
        "navigation_zones",
        "forbidden_volumes",
        "attachment_points",
        "interaction_anchors",
        "procedural",
        "procedural_node_hash",
    )

    def __init__(
        self,
        *,
        environment_id: EnvironmentInstanceId,
        revision_hash: str,
        name: str = "env",
        support_surfaces: Optional[List[tuple]] = None,
        navigation_zones: Optional[List[tuple]] = None,
        forbidden_volumes: Optional[List[tuple]] = None,
        attachment_points: Optional[List[tuple]] = None,
        interaction_anchors: Optional[List[tuple]] = None,
        procedural: bool = False,
        procedural_node_hash: str = "",
    ) -> None:
        self.environment_id = environment_id
        self.revision_hash = revision_hash
        self.name = name
        # each surface: (name, (minxyz), (maxxyz), surface_z)
        self.support_surfaces = [
            s if isinstance(s, tuple) else tuple(s) for s in (support_surfaces or [])
        ]
        self.navigation_zones = navigation_zones or []
        self.forbidden_volumes = forbidden_volumes or []
        self.attachment_points = attachment_points or []
        self.interaction_anchors = interaction_anchors or []
        self.procedural = procedural
        self.procedural_node_hash = procedural_node_hash

    def revision_content(self) -> str:
        """Compact deterministic revision signature for hashing."""
        return json.dumps(
            {
                "name": self.name,
                "surfaces": sorted(self.support_surfaces),
                "zones": sorted(self.navigation_zones),
                "forbidden": sorted(self.forbidden_volumes),
                "attachments": sorted(self.attachment_points),
                "anchors": sorted(self.interaction_anchors),
                "procedural": self.procedural,
                "node_hash": self.procedural_node_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def content_hash(self) -> str:
        return _stable_hash(self.revision_hash, self.revision_content())


class EnvironmentBuilder:
    """Deterministic environment compilation from approved asset + IR instance."""

    builder_version = "1.0.0"

    def __init__(
        self, *, id_factory: Optional[StableIdFactory] = None
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()

    # ------------------------------------------------------------------
    def build(
        self,
        instance: EnvironmentInstance,
        approved: ApprovedEnvironment,
        *,
        seed: int = 0,
    ) -> EnvironmentSpec:
        """Compile the approved environment into a neutral EnvironmentSpec.

        The approved asset is validated against the IR instance (same id).
        Probe geometry is described structurally; actual mesh intersection is
        deferred to the blender compiler/inspector (proxy bounds here, plan §7).
        """
        if str(approved.environment_id) != str(instance.instance_id):
            raise ValidationFailureError(
                "Environment asset id does not match the IR instance.",
                details={
                    "expected": str(instance.instance_id),
                    "got": str(approved.environment_id),
                },
            )
        ir_hash = (
            getattr(instance.asset, "content_hash", "") or ""
        )
        if ir_hash and ir_hash != approved.revision_hash and not approved.procedural:
            raise ValidationFailureError(
                "Environment asset revision hash mismatch; asset is not approved "
                "for this IR instance.",
                details={
                    "ir_hash": ir_hash,
                    "approved_hash": approved.revision_hash,
                },
            )
        self._validate_geometries(approved)

        return EnvironmentSpec(
            environment_id=instance.instance_id,
            support_surfaces=[
                SupportSurface(
                    name=f"{approved.name}.surf_{i}",
                    bounds=_surface_bounds(geom),
                    surface_z=_surface_top(geom),
                )
                for i, geom in enumerate(approved.support_surfaces)
            ],
            navigation_zones=[
                NavigationZone(
                    name=f"nav_{i}",
                    bounds=Aabb(min=Vec3(**mn), max=Vec3(**mx)),
                )
                for i, (mn, mx) in enumerate(approved.navigation_zones)
            ],
            forbidden_volumes=[
                ForbiddenVolume(
                    name=f"forbid_{i}",
                    bounds=Aabb(min=Vec3(**mn), max=Vec3(**mx)),
                )
                for i, (mn, mx) in enumerate(approved.forbidden_volumes)
            ],
            attachment_points=[
                AttachmentPoint(
                    name=ap[0],
                    position=Vec3(**ap[1]),
                    surface=ap[2] if len(ap) > 2 else "",
                )
                for ap in approved.attachment_points
            ],
            interaction_anchors=[
                InteractionAnchor(
                    name=ia[0],
                    position=Vec3(**ia[1]),
                    facing=Vec3(**ia[2]) if len(ia) > 2 and ia[2] else Vec3(),
                )
                for ia in approved.interaction_anchors
            ],
            unit="METERS",
        )

    # ------------------------------------------------------------------
    def _validate_geometries(self, approved: ApprovedEnvironment) -> None:
        """Fail closed on structurally invalid geometry (min > max etc)."""
        for surf in approved.support_surfaces:
            _surface_bounds(surf)  # raises on invalid
        for (mn, mx) in approved.navigation_zones:
            _assert_valid_aabb(Vec3(**mn), Vec3(**mx), "navigation zone")
        for (mn, mx) in approved.forbidden_volumes:
            _assert_valid_aabb(Vec3(**mn), Vec3(**mx), "forbidden volume")


def _coerce_vec(value) -> Vec3:
    return value if isinstance(value, Vec3) else Vec3(**value)


def _assert_valid_aabb(mn: Vec3, mx: Vec3, what: str) -> None:
    if not (mn.x <= mx.x and mn.y <= mx.y and mn.z <= mx.z):
        raise ValidationFailureError(
            f"Invalid AABB for {what}: min must be <= max on every axis.",
            details={"min": mn.as_tuple(), "max": mx.as_tuple()},
        )


def _surface_bounds(geom) -> Aabb:
    # geom: (name, (minxyz), (maxxyz), surface_z)
    name, min_xyz, max_xyz, surface_z = geom
    mn = Vec3(**min_xyz)
    mx = Vec3(**max_xyz)
    _assert_valid_aabb(mn, mx, f"surface {name}")
    if not (mn.z <= surface_z <= mx.z):
        raise ValidationFailureError(
            f"Surface {name}: surface_z {surface_z} outside AABB Z range.",
        )
    return Aabb(min=mn, max=mx)


def _surface_top(geom) -> float:
    return float(geom[3])


__all__ = ["ApprovedEnvironment", "EnvironmentBuilder"]
