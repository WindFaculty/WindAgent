"""
PropPlacementPlanner (VP3D Phase 12) — resolves IR props onto approved assets
placed at semantic anchors with a seeded, versioned scatter.

Determinism: every scatter uses the plan seed + a fixed algorithm version, so
the same seed/input produces the identical placement set. A placement version
bump (scatter_algorithm_version) changes outputs — versioning means a future
solver change invalidates only dependent scenes, never silently reproducers.

Fail closed: a prop whose approved asset hash is missing/unknown is recorded
as a typed finding and EXCLUDED from the plan (or raises for the composing
planner). Anonymous fallback (no approved hash) is never silently applied.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional
from windagent_core.domain.video_production.production_ir.models import (
    PropInstance,
)
from windagent_core.domain.video_production.set_dressing import (
    EnvironmentSpec,
    PropPlacement,
    SpatialFinding,
    SpatialFindingKind,
    Vec3,
)
from windagent_intelligence.video.ids import StableIdFactory

# Scatter algorithm version: bump to CHANGE deterministic placement output.
SCATTER_ALGORITHM_VERSION = "1.0.0"


class ApprovedProp:
    """An approved, content-addressed prop asset (revision hash + footprint)."""

    __slots__ = ("prop_id", "revision_hash", "name", "footprint")

    def __init__(self, *, prop_id, revision_hash: str, name: str = "prop",
                 footprint: Optional["Vec3"] = None) -> None:
        self.prop_id = prop_id
        self.revision_hash = revision_hash
        self.name = name
        # footprint = total size (x,y,z) used for AABB rejection sampling
        self.footprint = footprint or Vec3(x=1.0, y=1.0, z=1.0)


class PropPlacementPlanner:
    """Deterministic prop placement on semantic anchors with seeded scatter."""

    def __init__(self, *, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    # ------------------------------------------------------------------
    def place(
        self,
        props: List[PropInstance],
        approved: Dict[str, ApprovedProp],
        env: EnvironmentSpec,
        *,
        seed: int = 0,
        scatter_policy: str = "anchor",  # anchor | scatter
        count_per_anchor_desired: int = 1,
        findings_out: Optional[List[SpatialFinding]] = None,
    ) -> List[PropPlacement]:
        """Place approved props at anchors; unapproved props are excluded.

        - ``anchor`` policy: each prop with an ``anchor`` hint goes to that
          AttachmentPoint's position (deterministic).
        - ``scatter`` policy: props with no anchor are scattered across all
          attachment points using ``random.Random(seed)`` — deterministic
          because the seed + version are fixed.
        Missing approved asset => typed finding, prop excluded.
        """
        rng = random.Random(f"{seed}:{SCATTER_ALGORITHM_VERSION}")
        placements: List[PropPlacement] = []
        anchor_positions = {ap.name: ap.position for ap in env.attachment_points}
        anchor_names = list(anchor_positions.keys())

        for prop in props:
            key = str(prop.instance_id)
            approved_prop = approved.get(key) or approved.get(str(prop.prop_id))
            if approved_prop is None:
                if findings_out is not None:
                    findings_out.append(
                        SpatialFinding(
                            finding_id=self.id_factory.spatial_finding_id(
                                f"missing_{key}"
                            ),
                            kind=SpatialFindingKind.MISSING_APPROVED_ASSET,
                            entity=key,
                            detail="no approved prop asset for this IR prop",
                            blocking=True,
                        )
                    )
                continue

            hint = (prop.placement_hint or "").lower()
            # Empty hint OR scatter policy => deterministic scatter over anchors.
            if (not hint) or scatter_policy == "scatter":
                if not anchor_names:
                    if findings_out is not None:
                        findings_out.append(
                            SpatialFinding(
                                finding_id=self.id_factory.spatial_finding_id(
                                    f"noanchor_{key}"
                                ),
                                kind=SpatialFindingKind.OUT_OF_BOUNDS,
                                entity=key,
                                detail="no attachment points available to place prop",
                                blocking=True,
                            )
                        )
                    continue
                chosen = anchor_names[rng.randrange(len(anchor_names))]
                position = anchor_positions[chosen]
                anchor = chosen
            else:
                # Anchor-resolved placement. Deterministic: explicit position
                # hint wins; else the named anchor's position.
                anchor = hint
                if anchor in anchor_positions:
                    position = anchor_positions[anchor]
                elif isinstance(hint, str) and _looks_like_xyz(hint):
                    position = _parse_xyz(hint)
                    anchor = ""
                else:
                    if findings_out is not None:
                        findings_out.append(
                            SpatialFinding(
                                finding_id=self.id_factory.spatial_finding_id(
                                    f"hint_{key}"
                                ),
                                kind=SpatialFindingKind.OUT_OF_BOUNDS,
                                entity=key,
                                detail=f"anchor '{hint}' not found on environment",
                                blocking=True,
                            )
                        )
                    continue

            placements.append(
                PropPlacement(
                    prop_id=prop.instance_id,
                    asset_hash=approved_prop.revision_hash,
                    anchor=anchor,
                    position=position,
                    rotation_yaw=round(
                        (rng.randrange(0, 360) if scatter_policy == "scatter" else 0.0),
                        3,
                    ),
                    metadata={"name": approved_prop.name},
                )
            )

        return placements


def _looks_like_xyz(text: str) -> bool:
    parts = text.split(",")
    if len(parts) != 3:
        return False
    try:
        for part in parts:
            float(part)
    except ValueError:
        return False
    return True


def _parse_xyz(text: str) -> Vec3:
    parts = [float(p) for p in text.split(",")]
    return Vec3(x=parts[0], y=parts[1], z=parts[2])


__all__ = ["ApprovedProp", "PropPlacementPlanner", "SCATTER_ALGORITHM_VERSION"]
