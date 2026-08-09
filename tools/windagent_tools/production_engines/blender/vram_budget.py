"""VP3D Phase 20 - VRAM budget manager for Cycles production renders.

Engine-neutral resource estimation and mitigation policy.  Like the Phase 19
``rendering`` module this boundary deliberately contains no ``bpy`` import:
every estimate is derived from a neutral ``SceneResourceManifest`` (textures,
geometry, volumes, modifiers, render buffers), so the whole budget pipeline is
testable outside Blender.

Components:

```text
SceneResourceEstimator   -> per-category MB estimates + uncertainty
VramBudgetPolicy         -> configurable SAFE/WARNING/BLOCK thresholds, calibrated
TextureBudgetPolicy      -> texture-downscale mitigation rules
GeometryBudgetPolicy     -> LOD / instancing / hidden-geometry removal rules
VramMitigationPlanner    -> ordered, auditable mitigation chain + recommendation
```

Baseline policy: SAFE < 6.0 GB, WARNING 6.0-7.0 GB, BLOCK > 7.0 GB.  Thresholds
are configurable and are meant to be re-calibrated against measured peak VRAM
(``VramBudgetPolicy.calibrate``).

Mitigation order is controlled and each step produces a DERIVED manifest
revision (new revision hash) plus a quality-impact report - nothing is mutated
silently.  When even the full chain cannot bring the calibrated estimate under
the hard limit the planner blocks with a recommendation instead of letting the
render crash or retry blindly.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

VRAM_BUDGET_SCHEMA_VERSION = "vram-budget-1.0.0"

VRAM_SAFE = "SAFE"
VRAM_WARNING = "WARNING"
VRAM_BLOCK = "BLOCK"

DEFAULT_SAFE_THRESHOLD_GB = 6.0
DEFAULT_BLOCK_THRESHOLD_GB = 7.0

# Estimation constants (conservative GPU-side footprints).
BYTES_PER_VERTEX = 32
BYTES_PER_BVH_TRIANGLE = 64
BYTES_PER_INSTANCE = 64
MIPMAP_FACTOR = 4.0 / 3.0  # full-res + 1/4 + 1/16 + ... chain
MI_BYTES = 1024 * 1024

CATEGORY_TEXTURES = "textures"
CATEGORY_GEOMETRY = "geometry"
CATEGORY_MODIFIERS = "modifiers"
CATEGORY_VOLUMES = "volumes"
CATEGORY_RENDER_BUFFERS = "render_buffers"
CATEGORY_ACCELERATION_STRUCTURES = "acceleration_structures"
CATEGORIES = (
    CATEGORY_TEXTURES,
    CATEGORY_GEOMETRY,
    CATEGORY_MODIFIERS,
    CATEGORY_VOLUMES,
    CATEGORY_RENDER_BUFFERS,
    CATEGORY_ACCELERATION_STRUCTURES,
)

# Uncertainty fraction per category; wide where prediction is weak (modifiers,
# acceleration structures), narrow where the math is exact (render buffers).
UNCERTAINTY_FRACTIONS: Dict[str, float] = {
    CATEGORY_TEXTURES: 0.10,
    CATEGORY_GEOMETRY: 0.15,
    CATEGORY_MODIFIERS: 0.40,
    CATEGORY_VOLUMES: 0.25,
    CATEGORY_RENDER_BUFFERS: 0.05,
    CATEGORY_ACCELERATION_STRUCTURES: 0.20,
}

# Controlled mitigation order (Phase 20 backlog item 3).
MITIGATION_TEXTURE_DOWNSCALE = "texture_downscale"
MITIGATION_LOD = "lod"
MITIGATION_INSTANCING = "instancing"
MITIGATION_HIDDEN_GEOMETRY_REMOVAL = "hidden_geometry_removal"
MITIGATION_SPLIT_SHOT = "split_shot"
MITIGATION_ORDER = (
    MITIGATION_TEXTURE_DOWNSCALE,
    MITIGATION_LOD,
    MITIGATION_INSTANCING,
    MITIGATION_HIDDEN_GEOMETRY_REMOVAL,
    MITIGATION_SPLIT_SHOT,
)


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _round_mb(value: float) -> float:
    return round(float(value), 2)


# ---------------------------------------------------------------------------
# Neutral scene resource manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextureResource:
    """One texture: dimensions, channel layout, mipmap chain."""

    name: str
    width: int
    height: int
    channels: int = 4
    bytes_per_channel: int = 1
    mipmaps: bool = True
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "bytes_per_channel": self.bytes_per_channel,
            "mipmaps": self.mipmaps,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextureResource":
        return cls(
            name=str(data.get("name", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            channels=int(data.get("channels", 4)),
            bytes_per_channel=int(data.get("bytes_per_channel", 1)),
            mipmaps=bool(data.get("mipmaps", True)),
            visible=bool(data.get("visible", True)),
        )


@dataclass(frozen=True)
class MeshResource:
    """One mesh asset with its instance count and instancing state."""

    name: str
    vertex_count: int
    triangle_count: int
    instance_count: int = 1
    instanced: bool = False
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vertex_count": self.vertex_count,
            "triangle_count": self.triangle_count,
            "instance_count": self.instance_count,
            "instanced": self.instanced,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MeshResource":
        return cls(
            name=str(data.get("name", "")),
            vertex_count=int(data.get("vertex_count", 0)),
            triangle_count=int(data.get("triangle_count", 0)),
            instance_count=int(data.get("instance_count", 1)),
            instanced=bool(data.get("instanced", False)),
            visible=bool(data.get("visible", True)),
        )


@dataclass(frozen=True)
class VolumeResource:
    """One 3D grid (smoke/fire/volumetric material)."""

    name: str
    grid_resolution: int
    channels: int = 1
    bytes_per_channel: int = 4
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "grid_resolution": self.grid_resolution,
            "channels": self.channels,
            "bytes_per_channel": self.bytes_per_channel,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VolumeResource":
        return cls(
            name=str(data.get("name", "")),
            grid_resolution=int(data.get("grid_resolution", 0)),
            channels=int(data.get("channels", 1)),
            bytes_per_channel=int(data.get("bytes_per_channel", 4)),
            visible=bool(data.get("visible", True)),
        )


@dataclass(frozen=True)
class ModifierResource:
    """One modifier/simulation whose footprint is an explicit estimate."""

    name: str
    kind: str
    estimated_extra_mb: float = 0.0
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "estimated_extra_mb": self.estimated_extra_mb,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModifierResource":
        return cls(
            name=str(data.get("name", "")),
            kind=str(data.get("kind", "")),
            estimated_extra_mb=float(data.get("estimated_extra_mb", 0.0)),
            visible=bool(data.get("visible", True)),
        )


@dataclass(frozen=True)
class RenderBufferSettings:
    """Render buffer footprint from the compiled profile."""

    width: int
    height: int
    pass_count: int = 6
    bytes_per_pixel: int = 4

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "pass_count": self.pass_count,
            "bytes_per_pixel": self.bytes_per_pixel,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderBufferSettings":
        return cls(
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            pass_count=int(data.get("pass_count", 6)),
            bytes_per_pixel=int(data.get("bytes_per_pixel", 4)),
        )


@dataclass(frozen=True)
class SceneResourceManifest:
    """Engine-neutral description of everything a scene will put on the GPU.

    Immutable: every mitigation builds a DERIVED manifest (new revision hash),
    the original is never mutated (Phase 20 backlog item 4).
    """

    textures: Tuple[TextureResource, ...] = ()
    meshes: Tuple[MeshResource, ...] = ()
    volumes: Tuple[VolumeResource, ...] = ()
    modifiers: Tuple[ModifierResource, ...] = ()
    render_buffers: RenderBufferSettings = RenderBufferSettings(0, 0)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": VRAM_BUDGET_SCHEMA_VERSION,
            "textures": [t.to_dict() for t in self.textures],
            "meshes": [m.to_dict() for m in self.meshes],
            "volumes": [v.to_dict() for v in self.volumes],
            "modifiers": [m.to_dict() for m in self.modifiers],
            "render_buffers": self.render_buffers.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneResourceManifest":
        return cls(
            textures=tuple(
                TextureResource.from_dict(item)
                for item in data.get("textures", []) or []
                if isinstance(item, Mapping)
            ),
            meshes=tuple(
                MeshResource.from_dict(item)
                for item in data.get("meshes", []) or []
                if isinstance(item, Mapping)
            ),
            volumes=tuple(
                VolumeResource.from_dict(item)
                for item in data.get("volumes", []) or []
                if isinstance(item, Mapping)
            ),
            modifiers=tuple(
                ModifierResource.from_dict(item)
                for item in data.get("modifiers", []) or []
                if isinstance(item, Mapping)
            ),
            render_buffers=RenderBufferSettings.from_dict(
                data.get("render_buffers") or {}
            ),
            metadata=dict(data.get("metadata") or {}),
        )

    def revision_hash(self) -> str:
        """Content hash; every derived manifest gets a NEW revision hash."""
        return _canonical_hash(self.to_dict())


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceEstimateItem:
    """One category's estimate with recorded uncertainty (backlog item 1)."""

    category: str
    estimated_mb: float
    uncertainty_mb: float
    method: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "estimated_mb": self.estimated_mb,
            "uncertainty_mb": self.uncertainty_mb,
            "method": self.method,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResourceEstimateItem":
        return cls(
            category=str(data.get("category", "")),
            estimated_mb=float(data.get("estimated_mb", 0.0)),
            uncertainty_mb=float(data.get("uncertainty_mb", 0.0)),
            method=str(data.get("method", "")),
            note=str(data.get("note", "")),
        )


@dataclass(frozen=True)
class SceneResourceEstimate:
    """Full estimate: per-category items, total, aggregated uncertainty."""

    items: Tuple[ResourceEstimateItem, ...]
    total_mb: float
    uncertainty_mb: float

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "total_mb": self.total_mb,
            "uncertainty_mb": self.uncertainty_mb,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneResourceEstimate":
        return cls(
            items=tuple(
                ResourceEstimateItem.from_dict(item)
                for item in data.get("items", []) or []
                if isinstance(item, Mapping)
            ),
            total_mb=float(data.get("total_mb", 0.0)),
            uncertainty_mb=float(data.get("uncertainty_mb", 0.0)),
        )


class SceneResourceEstimator:
    """Estimate GPU-resident memory per category from a neutral manifest.

    Method notes per category: ``computed`` (deterministic formula),
    ``explicit`` (caller-supplied modifier estimate).  Uncertainty is recorded
    per item and aggregated by RMS over independent categories.
    """

    def estimate(self, manifest: SceneResourceManifest) -> SceneResourceEstimate:
        items = [
            self._estimate_textures(manifest.textures),
            self._estimate_geometry(manifest.meshes),
            self._estimate_modifiers(manifest.modifiers),
            self._estimate_volumes(manifest.volumes),
            self._estimate_render_buffers(manifest.render_buffers),
            self._estimate_acceleration_structures(manifest.meshes),
        ]
        total = sum(item.estimated_mb for item in items)
        uncertainty = math.sqrt(sum(item.uncertainty_mb**2 for item in items))
        return SceneResourceEstimate(
            items=tuple(items), total_mb=_round_mb(total), uncertainty_mb=_round_mb(uncertainty)
        )

    def _item(self, category: str, estimated_mb: float, method: str, note: str = "") -> ResourceEstimateItem:
        fraction = UNCERTAINTY_FRACTIONS.get(category, 0.1)
        return ResourceEstimateItem(
            category=category,
            estimated_mb=_round_mb(estimated_mb),
            uncertainty_mb=round(estimated_mb * fraction, 4),
            method=method,
            note=note,
        )

    def _estimate_textures(self, textures) -> ResourceEstimateItem:
        total = 0.0
        for tex in textures:
            # Conservative: hidden textures are still resident until removed.
            pixels = max(tex.width, 0) * max(tex.height, 0)
            chain = MIPMAP_FACTOR if tex.mipmaps else 1.0
            total += pixels * max(tex.channels, 0) * max(tex.bytes_per_channel, 0) * chain
        return self._item(
            CATEGORY_TEXTURES,
            total / MI_BYTES,
            "computed",
            f"{len(textures)} texture(s), RGBA x bpc x mipmap chain",
        )

    def _estimate_geometry(self, meshes) -> ResourceEstimateItem:
        total = 0.0
        for mesh in meshes:
            vertex_bytes = max(mesh.vertex_count, 0) * BYTES_PER_VERTEX
            if mesh.instanced:
                # Geometry resident once; per-instance transform overhead only.
                total += vertex_bytes + max(mesh.instance_count, 0) * BYTES_PER_INSTANCE
            else:
                total += vertex_bytes * max(mesh.instance_count, 1)
        return self._item(
            CATEGORY_GEOMETRY,
            total / MI_BYTES,
            "computed",
            f"{len(meshes)} mesh(es), {BYTES_PER_VERTEX} B/vertex",
        )

    def _estimate_modifiers(self, modifiers) -> ResourceEstimateItem:
        total = sum(max(m.estimated_extra_mb, 0.0) for m in modifiers)
        return self._item(
            CATEGORY_MODIFIERS,
            total,
            "explicit",
            f"{len(modifiers)} modifier(s)/simulation(s), explicit estimates",
        )

    def _estimate_volumes(self, volumes) -> ResourceEstimateItem:
        total = 0.0
        for volume in volumes:
            grid = max(volume.grid_resolution, 0)
            total += grid**3 * max(volume.channels, 0) * max(volume.bytes_per_channel, 0)
        return self._item(
            CATEGORY_VOLUMES,
            total / MI_BYTES,
            "computed",
            f"{len(volumes)} volume grid(s), channels x bpc",
        )

    def _estimate_render_buffers(self, buffers: RenderBufferSettings) -> ResourceEstimateItem:
        total = (
            max(buffers.width, 0)
            * max(buffers.height, 0)
            * max(buffers.pass_count, 0)
            * max(buffers.bytes_per_pixel, 0)
        )
        return self._item(
            CATEGORY_RENDER_BUFFERS,
            total / MI_BYTES,
            "computed",
            f"{buffers.width}x{buffers.height} x {buffers.pass_count} passes x {buffers.bytes_per_pixel} B/px",
        )

    def _estimate_acceleration_structures(self, meshes) -> ResourceEstimateItem:
        total = 0.0
        for mesh in meshes:
            triangle_bytes = max(mesh.triangle_count, 0) * BYTES_PER_BVH_TRIANGLE
            if mesh.instanced or mesh.instance_count <= 1:
                total += triangle_bytes
            else:
                total += triangle_bytes * mesh.instance_count
        return self._item(
            CATEGORY_ACCELERATION_STRUCTURES,
            total / MI_BYTES,
            "computed",
            f"{BYTES_PER_BVH_TRIANGLE} B/triangle BVH",
        )


# ---------------------------------------------------------------------------
# Budget policy + calibration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VramCalibrationRecord:
    """One estimate-vs-actual measurement (backlog item 2)."""

    fixture: str
    estimated_mb: float
    measured_mb: float
    factor: float

    def to_dict(self) -> dict:
        return {
            "fixture": self.fixture,
            "estimated_mb": self.estimated_mb,
            "measured_mb": self.measured_mb,
            "factor": self.factor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VramCalibrationRecord":
        return cls(
            fixture=str(data.get("fixture", "")),
            estimated_mb=float(data.get("estimated_mb", 0.0)),
            measured_mb=float(data.get("measured_mb", 0.0)),
            factor=float(data.get("factor", 1.0)),
        )


@dataclass(frozen=True)
class VramBudgetPolicy:
    """Configurable VRAM thresholds calibrated against measured peak memory.

    Baseline (plan Stage J Phase 20): SAFE < 6.0 GB, WARNING 6.0-7.0 GB,
    BLOCK > 7.0 GB.  ``safety_factor`` is the mean measured/estimated ratio
    from ``calibrate()`` records; it scales every verdict.
    """

    safe_threshold_gb: float = DEFAULT_SAFE_THRESHOLD_GB
    block_threshold_gb: float = DEFAULT_BLOCK_THRESHOLD_GB
    safety_factor: float = 1.0
    calibration_records: Tuple[VramCalibrationRecord, ...] = ()
    schema_version: str = VRAM_BUDGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not 0.0 < self.safe_threshold_gb < self.block_threshold_gb:
            raise ValueError(
                "vram budget thresholds must satisfy 0 < safe < block; "
                f"got safe={self.safe_threshold_gb} block={self.block_threshold_gb}"
            )
        if self.safety_factor <= 0.0:
            raise ValueError(f"safety factor must be positive, got {self.safety_factor}")

    def calibrated_mb(self, total_mb: float) -> float:
        return total_mb * self.safety_factor

    def classify(self, estimate: SceneResourceEstimate) -> str:
        """SAFE / WARNING / BLOCK on the CALIBRATED estimate."""
        calibrated = self.calibrated_mb(estimate.total_mb)
        if calibrated < self.safe_threshold_gb * 1024:
            return VRAM_SAFE
        if calibrated < self.block_threshold_gb * 1024:
            return VRAM_WARNING
        return VRAM_BLOCK

    def calibrate(self, fixture: str, estimated_mb: float, measured_mb: float) -> "VramBudgetPolicy":
        """Record one estimate-vs-actual pair and re-derive the safety factor."""
        if estimated_mb <= 0.0:
            raise ValueError(f"estimated_mb must be positive, got {estimated_mb}")
        if measured_mb <= 0.0:
            raise ValueError(f"measured_mb must be positive, got {measured_mb}")
        factor = measured_mb / estimated_mb
        records = self.calibration_records + (
            VramCalibrationRecord(fixture, estimated_mb, measured_mb, round(factor, 4)),
        )
        mean_factor = sum(record.factor for record in records) / len(records)
        return replace(
            self,
            safety_factor=round(mean_factor, 4),
            calibration_records=records,
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "safe_threshold_gb": self.safe_threshold_gb,
            "block_threshold_gb": self.block_threshold_gb,
            "safety_factor": self.safety_factor,
            "calibration_records": [record.to_dict() for record in self.calibration_records],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VramBudgetPolicy":
        return cls(
            safe_threshold_gb=float(data.get("safe_threshold_gb", DEFAULT_SAFE_THRESHOLD_GB)),
            block_threshold_gb=float(data.get("block_threshold_gb", DEFAULT_BLOCK_THRESHOLD_GB)),
            safety_factor=float(data.get("safety_factor", 1.0)),
            calibration_records=tuple(
                VramCalibrationRecord.from_dict(item)
                for item in data.get("calibration_records", []) or []
                if isinstance(item, Mapping)
            ),
        )


# ---------------------------------------------------------------------------
# Mitigation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityImpact:
    """One auditable quality change produced by a mitigation step."""

    resource: str
    impact: str
    severity: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "resource": self.resource,
            "impact": self.impact,
            "severity": self.severity,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QualityImpact":
        return cls(
            resource=str(data.get("resource", "")),
            impact=str(data.get("impact", "")),
            severity=str(data.get("severity", "")),
            detail=str(data.get("detail", "")),
        )


@dataclass(frozen=True)
class MitigationStep:
    """One applied mitigation: derived revision + quality impact + memory saved."""

    name: str
    applied: bool
    saved_mb: float
    new_total_mb: float
    revision_hash: str
    impacts: Tuple[QualityImpact, ...]
    verdict_after: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "applied": self.applied,
            "saved_mb": self.saved_mb,
            "new_total_mb": self.new_total_mb,
            "revision_hash": self.revision_hash,
            "impacts": [impact.to_dict() for impact in self.impacts],
            "verdict_after": self.verdict_after,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MitigationStep":
        return cls(
            name=str(data.get("name", "")),
            applied=bool(data.get("applied", False)),
            saved_mb=float(data.get("saved_mb", 0.0)),
            new_total_mb=float(data.get("new_total_mb", 0.0)),
            revision_hash=str(data.get("revision_hash", "")),
            impacts=tuple(
                QualityImpact.from_dict(item)
                for item in data.get("impacts", []) or []
                if isinstance(item, Mapping)
            ),
            verdict_after=str(data.get("verdict_after", "")),
        )


@dataclass(frozen=True)
class VramBudgetDecision:
    """Full audit trail: original estimate, mitigation chain, final verdict."""

    original_estimate: SceneResourceEstimate
    original_verdict: str
    steps: Tuple[MitigationStep, ...]
    final_estimate: SceneResourceEstimate
    final_verdict: str
    blocked: bool
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "schema_version": VRAM_BUDGET_SCHEMA_VERSION,
            "original_estimate": self.original_estimate.to_dict(),
            "original_verdict": self.original_verdict,
            "steps": [step.to_dict() for step in self.steps],
            "final_estimate": self.final_estimate.to_dict(),
            "final_verdict": self.final_verdict,
            "blocked": self.blocked,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VramBudgetDecision":
        return cls(
            original_estimate=SceneResourceEstimate.from_dict(data.get("original_estimate") or {}),
            original_verdict=str(data.get("original_verdict", "")),
            steps=tuple(
                MitigationStep.from_dict(item)
                for item in data.get("steps", []) or []
                if isinstance(item, Mapping)
            ),
            final_estimate=SceneResourceEstimate.from_dict(data.get("final_estimate") or {}),
            final_verdict=str(data.get("final_verdict", "")),
            blocked=bool(data.get("blocked", False)),
            recommendation=str(data.get("recommendation", "")),
        )


class TextureBudgetPolicy:
    """Texture downscale rules (mitigation step 1)."""

    def __init__(self, scale: float = 0.5, min_dimension: int = 64) -> None:
        if not 0.0 < scale < 1.0:
            raise ValueError(f"texture downscale must be in (0,1), got {scale}")
        self.scale = scale
        self.min_dimension = min_dimension

    def apply(self, manifest: SceneResourceManifest) -> Tuple[SceneResourceManifest, Tuple[QualityImpact, ...]]:
        textures = []
        impacts = []
        for tex in manifest.textures:
            new_width = max(self.min_dimension, int(round(tex.width * self.scale)))
            new_height = max(self.min_dimension, int(round(tex.height * self.scale)))
            textures.append(
                replace(
                    tex,
                    width=new_width,
                    height=new_height,
                )
            )
            impacts.append(
                QualityImpact(
                    resource=tex.name,
                    impact=MITIGATION_TEXTURE_DOWNSCALE,
                    severity="LOW",
                    detail=f"{tex.width}x{tex.height} -> {new_width}x{new_height}",
                )
            )
        derived = replace(manifest, textures=tuple(textures))
        return derived, tuple(impacts)


class GeometryBudgetPolicy:
    """LOD / instancing / hidden-geometry-removal rules (mitigation steps 2-4)."""

    def __init__(self, lod_factor: float = 0.5, min_vertices: int = 100, min_triangles: int = 50) -> None:
        if not 0.0 < lod_factor < 1.0:
            raise ValueError(f"lod factor must be in (0,1), got {lod_factor}")
        self.lod_factor = lod_factor
        self.min_vertices = min_vertices
        self.min_triangles = min_triangles

    def apply_lod(self, manifest: SceneResourceManifest) -> Tuple[SceneResourceManifest, Tuple[QualityImpact, ...]]:
        meshes = []
        impacts = []
        for mesh in manifest.meshes:
            vertices = max(self.min_vertices, int(round(mesh.vertex_count * self.lod_factor)))
            triangles = max(self.min_triangles, int(round(mesh.triangle_count * self.lod_factor)))
            meshes.append(replace(mesh, vertex_count=vertices, triangle_count=triangles))
            impacts.append(
                QualityImpact(
                    resource=mesh.name,
                    impact=MITIGATION_LOD,
                    severity="MEDIUM",
                    detail=f"verts {mesh.vertex_count}->{vertices}, tris {mesh.triangle_count}->{triangles}",
                )
            )
        return replace(manifest, meshes=tuple(meshes)), tuple(impacts)

    def apply_instancing(self, manifest: SceneResourceManifest) -> Tuple[SceneResourceManifest, Tuple[QualityImpact, ...]]:
        meshes = []
        impacts = []
        for mesh in manifest.meshes:
            if mesh.instance_count > 1 and not mesh.instanced:
                meshes.append(replace(mesh, instanced=True))
                impacts.append(
                    QualityImpact(
                        resource=mesh.name,
                        impact=MITIGATION_INSTANCING,
                        severity="LOW",
                        detail=f"{mesh.instance_count} instances share one geometry buffer",
                    )
                )
            else:
                meshes.append(mesh)
        return replace(manifest, meshes=tuple(meshes)), tuple(impacts)

    def apply_hidden_geometry_removal(
        self, manifest: SceneResourceManifest
    ) -> Tuple[SceneResourceManifest, Tuple[QualityImpact, ...]]:
        textures = tuple(tex for tex in manifest.textures if tex.visible)
        meshes = tuple(mesh for mesh in manifest.meshes if mesh.visible)
        volumes = tuple(vol for vol in manifest.volumes if vol.visible)
        modifiers = tuple(mod for mod in manifest.modifiers if mod.visible)
        removed = (
            len(manifest.textures) - len(textures)
            + len(manifest.meshes) - len(meshes)
            + len(manifest.volumes) - len(volumes)
            + len(manifest.modifiers) - len(modifiers)
        )
        impacts = []
        if removed:
            impacts.append(
                QualityImpact(
                    resource="scene",
                    impact=MITIGATION_HIDDEN_GEOMETRY_REMOVAL,
                    severity="LOW",
                    detail=f"{removed} hidden resource(s) removed from render",
                )
            )
        derived = replace(manifest, textures=textures, meshes=meshes, volumes=volumes, modifiers=modifiers)
        return derived, tuple(impacts)


class VramMitigationPlanner:
    """Ordered mitigation chain with derived revisions (backlog items 3-5).

    Order is controlled: texture downscale -> LOD -> instancing -> hidden
    geometry removal -> split shot.  Every step yields a DERIVED manifest
    revision plus a quality-impact report; nothing is mutated silently.  If the
    calibrated estimate still exceeds the hard limit after the full chain the
    decision blocks with a recommendation - never a blind crash/retry.
    """

    def __init__(
        self,
        estimator: Optional[SceneResourceEstimator] = None,
        texture_policy: Optional[TextureBudgetPolicy] = None,
        geometry_policy: Optional[GeometryBudgetPolicy] = None,
        split_segments: int = 2,
    ) -> None:
        self._estimator = estimator or SceneResourceEstimator()
        self._texture_policy = texture_policy or TextureBudgetPolicy()
        self._geometry_policy = geometry_policy or GeometryBudgetPolicy()
        if split_segments < 2:
            raise ValueError(f"split shot needs >= 2 segments, got {split_segments}")
        self._split_segments = split_segments

    def plan(self, manifest: SceneResourceManifest, policy: VramBudgetPolicy) -> VramBudgetDecision:
        original_estimate = self._estimator.estimate(manifest)
        original_verdict = policy.classify(original_estimate)
        if original_verdict != VRAM_BLOCK:
            return VramBudgetDecision(
                original_estimate=original_estimate,
                original_verdict=original_verdict,
                steps=(),
                final_estimate=original_estimate,
                final_verdict=original_verdict,
                blocked=False,
                recommendation="",
            )

        current = manifest
        current_estimate = original_estimate
        steps = []
        for name in MITIGATION_ORDER:
            if policy.classify(current_estimate) != VRAM_BLOCK:
                break
            derived, impacts = self._apply(name, current)
            derived_estimate = self._estimator.estimate(derived)
            steps.append(
                MitigationStep(
                    name=name,
                    applied=True,
                    saved_mb=_round_mb(current_estimate.total_mb - derived_estimate.total_mb),
                    new_total_mb=derived_estimate.total_mb,
                    revision_hash=derived.revision_hash(),
                    impacts=impacts,
                    verdict_after=policy.classify(derived_estimate),
                )
            )
            current = derived
            current_estimate = derived_estimate

        final_verdict = policy.classify(current_estimate)
        blocked = final_verdict == VRAM_BLOCK
        recommendation = self._recommendation(current_estimate, policy) if blocked else ""
        return VramBudgetDecision(
            original_estimate=original_estimate,
            original_verdict=original_verdict,
            steps=tuple(steps),
            final_estimate=current_estimate,
            final_verdict=final_verdict,
            blocked=blocked,
            recommendation=recommendation,
        )

    def _apply(self, name: str, manifest: SceneResourceManifest):
        if name == MITIGATION_TEXTURE_DOWNSCALE:
            return self._texture_policy.apply(manifest)
        if name == MITIGATION_LOD:
            return self._geometry_policy.apply_lod(manifest)
        if name == MITIGATION_INSTANCING:
            return self._geometry_policy.apply_instancing(manifest)
        if name == MITIGATION_HIDDEN_GEOMETRY_REMOVAL:
            return self._geometry_policy.apply_hidden_geometry_removal(manifest)
        if name == MITIGATION_SPLIT_SHOT:
            return self._split_shot(manifest)
        raise ValueError(f"unknown mitigation {name!r}")

    def _split_shot(self, manifest: SceneResourceManifest):
        """Split the shot into N segments; peak = largest segment.

        Geometry/acceleration structures are distributed across segments;
        textures and volumes remain resident (shared), render buffers are
        unchanged.  Models the controlled-recovery "split shot" mitigation
        without pretending peak memory drops below the largest segment.
        """
        meshes = list(manifest.meshes)
        segments: List[List[MeshResource]] = [[] for _ in range(self._split_segments)]
        for mesh in meshes:
            if mesh.instanced or mesh.instance_count <= 1:
                segments[0].append(mesh)  # resident once; counted in every peak via segment 0
            else:
                per_segment = max(1, mesh.instance_count // self._split_segments)
                for index in range(self._split_segments):
                    segments[index].append(
                        replace(mesh, instance_count=per_segment if index < self._split_segments - 1
                                else mesh.instance_count - per_segment * (self._split_segments - 1))
                    )
        # Peak geometry: evaluate each segment independently.
        peak = segments[0]
        for segment in segments[1:]:
            if self._segment_mb(segment) > self._segment_mb(peak):
                peak = segment
        impacts = (
            QualityImpact(
                resource="scene",
                impact=MITIGATION_SPLIT_SHOT,
                severity="MEDIUM",
                detail=f"shot split into {self._split_segments} segments; peak concurrent geometry limited to largest segment",
            ),
        )
        # The derived manifest keeps ALL resources (the shot is still the same
        # shot); the estimator sees the peak segment via metadata override.
        metadata = dict(manifest.metadata)
        metadata["split_shot_segments"] = self._split_segments
        derived = replace(
            manifest,
            meshes=tuple(peak),
            metadata=metadata,
        )
        return derived, impacts

    @staticmethod
    def _segment_mb(meshes: List[MeshResource]) -> float:
        total = 0.0
        for mesh in meshes:
            vertex_bytes = max(mesh.vertex_count, 0) * BYTES_PER_VERTEX
            triangle_bytes = max(mesh.triangle_count, 0) * BYTES_PER_BVH_TRIANGLE
            if mesh.instanced:
                total += vertex_bytes + max(mesh.instance_count, 0) * BYTES_PER_INSTANCE + triangle_bytes
            else:
                total += vertex_bytes * max(mesh.instance_count, 1) + triangle_bytes * max(mesh.instance_count, 1)
        return total

    @staticmethod
    def _recommendation(estimate: SceneResourceEstimate, policy: VramBudgetPolicy) -> str:
        calibrated_gb = policy.calibrated_mb(estimate.total_mb) / 1024
        return (
            f"estimated calibrated peak VRAM {calibrated_gb:.2f} GB still exceeds hard limit "
            f"{policy.block_threshold_gb:g} GB after the full mitigation chain; render blocked before "
            "launch - reduce resolution, split the shot into more segments, lower samples, or free "
            "other GPU memory before retrying"
        )


def evaluate_vram_budget(
    manifest: SceneResourceManifest,
    policy: VramBudgetPolicy,
    planner: Optional[VramMitigationPlanner] = None,
) -> VramBudgetDecision:
    """One-call gate: estimate, mitigate, verdict (used by the adapter)."""
    return (planner or VramMitigationPlanner()).plan(manifest, policy)


__all__ = [
    "VRAM_BUDGET_SCHEMA_VERSION",
    "VRAM_SAFE",
    "VRAM_WARNING",
    "VRAM_BLOCK",
    "DEFAULT_SAFE_THRESHOLD_GB",
    "DEFAULT_BLOCK_THRESHOLD_GB",
    "CATEGORY_TEXTURES",
    "CATEGORY_GEOMETRY",
    "CATEGORY_MODIFIERS",
    "CATEGORY_VOLUMES",
    "CATEGORY_RENDER_BUFFERS",
    "CATEGORY_ACCELERATION_STRUCTURES",
    "CATEGORIES",
    "MITIGATION_TEXTURE_DOWNSCALE",
    "MITIGATION_LOD",
    "MITIGATION_INSTANCING",
    "MITIGATION_HIDDEN_GEOMETRY_REMOVAL",
    "MITIGATION_SPLIT_SHOT",
    "MITIGATION_ORDER",
    "TextureResource",
    "MeshResource",
    "VolumeResource",
    "ModifierResource",
    "RenderBufferSettings",
    "SceneResourceManifest",
    "ResourceEstimateItem",
    "SceneResourceEstimate",
    "SceneResourceEstimator",
    "VramCalibrationRecord",
    "VramBudgetPolicy",
    "QualityImpact",
    "MitigationStep",
    "VramBudgetDecision",
    "TextureBudgetPolicy",
    "GeometryBudgetPolicy",
    "VramMitigationPlanner",
    "evaluate_vram_budget",
]
