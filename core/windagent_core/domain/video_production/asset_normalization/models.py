"""
Provider-neutral DTOs for asset normalization (VP3D Phase 7, Stage C).

Every model is frozen and engine-agnostic: no ``bpy``, no provider SDK, no
transport object ever appears here. The normalization pipeline consumes a
content-addressed ``ReferenceAsset`` and produces an immutable normalized
``AssetBundle`` (interchange file + textures + preview + manifest + provenance
+ validation report) with a deterministic bundle hash.

All hard-limit checks (polygon count, texture resolution, VRAM estimate) fail
closed BEFORE any preview render is attempted: an over-budget asset is
``BLOCKED``, never blindly rendered.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.asset_resolution.models import (
    DEFAULT_MAX_POLYGONS,
    DEFAULT_MAX_TEXTURE_RESOLUTION,
    DEFAULT_MAX_VRAM_ESTIMATE_BYTES,
    AssetRequirement,
)
from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    ColorSpace,
    LodPolicy,
    NormalizationStage,
    NormalizationStatus,
    StageStatus,
    UnitSystem,
    UpAxis,
    VramDecision,
)
from windagent_core.domain.video_production.ids import NormalizationRunId


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Default preview profile: deterministic Blender profile of Stage B
# (Cycles, locked samples, CPU fallback, Standard color management).
DEFAULT_PREVIEW_WIDTH = 512
DEFAULT_PREVIEW_HEIGHT = 288
DEFAULT_PREVIEW_SAMPLES = 8
DEFAULT_PREVIEW_FRAMES = 12


class PreviewProfile(BaseModel):
    """Locked deterministic profile for turntable/thumbnail preview renders."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int = Field(default=DEFAULT_PREVIEW_WIDTH, ge=64, le=4096)
    height: int = Field(default=DEFAULT_PREVIEW_HEIGHT, ge=64, le=4096)
    frames: int = Field(default=DEFAULT_PREVIEW_FRAMES, ge=1, le=120)
    samples: int = Field(default=DEFAULT_PREVIEW_SAMPLES, ge=1, le=4096)
    engine: str = "CYCLES"
    device: str = "CPU"
    color_management: str = "Standard"
    denoise: bool = False

    @property
    def resolution(self) -> List[int]:
        return [self.width, self.height]


class NormalizationConfig(BaseModel):
    """Canonical target profile every asset is normalized toward."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_unit: UnitSystem = UnitSystem.METERS
    target_up_axis: UpAxis = UpAxis.Z_UP
    lod_policy: LodPolicy = LodPolicy.SINGLE
    max_texture_resolution: int = Field(
        default=DEFAULT_MAX_TEXTURE_RESOLUTION, ge=64, le=16384
    )
    max_texture_bit_depth: int = Field(default=16, ge=8, le=32)
    max_polygons: int = Field(default=DEFAULT_MAX_POLYGONS, ge=1)
    max_vram_bytes: int = Field(default=DEFAULT_MAX_VRAM_ESTIMATE_BYTES, ge=1)
    downscale_textures: bool = True
    preview: PreviewProfile = Field(default_factory=PreviewProfile)
    lod_ratios: List[float] = Field(default_factory=lambda: [0.5, 0.2])
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StageRecord(BaseModel):
    """Outcome + timing of ONE pipeline stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: NormalizationStage
    status: StageStatus
    started_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(default=0, ge=0)
    detail: str = ""


class NormalizationReport(BaseModel):
    """Full per-stage report of one normalization run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: List[StageRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    def stage_status(self, stage: NormalizationStage) -> Optional[StageStatus]:
        for record in self.stages:
            if record.stage == stage:
                return record.status
        return None


class CanonicalMetadata(BaseModel):
    """Canonical scene metadata after unit/axis normalization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    unit: UnitSystem = UnitSystem.METERS
    up_axis: UpAxis = UpAxis.Z_UP
    scale_factor: float = Field(default=1.0, gt=0)  # source unit -> meters
    detected_unit: UnitSystem = UnitSystem.UNKNOWN
    detected_up_axis: UpAxis = UpAxis.UNKNOWN
    axis_converted: bool = False
    unit_converted: bool = False

    @model_validator(mode="before")
    @classmethod
    def _derive_from_detected(cls, data: Any) -> Any:
        """Derive scale/conversion flags from the detected values (fail closed:
        an UNKNOWN detected unit is assumed meters — no silent rescaling)."""
        if not isinstance(data, dict):
            return data
        detected_unit = data.get("detected_unit", UnitSystem.UNKNOWN)
        detected_up_axis = data.get("detected_up_axis", UpAxis.UNKNOWN)
        data = dict(data)
        data["scale_factor"] = detected_unit.meters_per_unit
        data["unit_converted"] = detected_unit is not UnitSystem.METERS
        data["axis_converted"] = detected_up_axis is not UpAxis.Z_UP
        return data


class MeshValidationReport(BaseModel):
    """Structural mesh validation findings (blocking issues fail the asset)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    object_count: int = Field(default=0, ge=0)
    vertex_count: int = Field(default=0, ge=0)
    triangle_count: int = Field(default=0, ge=0)
    non_manifold_edges: int = Field(default=0, ge=0)
    non_manifold_vertices: int = Field(default=0, ge=0)
    degenerate_faces: int = Field(default=0, ge=0)
    inverted_normals: int = Field(default=0, ge=0)
    missing_uv_layers: List[str] = Field(default_factory=list)
    missing_textures: List[str] = Field(default_factory=list)
    unsupported_shaders: List[str] = Field(default_factory=list)
    armatures: List[str] = Field(default_factory=list)
    animation_clips: List[str] = Field(default_factory=list)
    skeleton_ok: bool = True
    topology_compliant: bool = True
    blocking_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class TextureInfo(BaseModel):
    """One normalized, content-addressed texture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = ""
    content_hash: str = Field(min_length=64, max_length=64)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    bit_depth: int = Field(ge=1)
    color_space: ColorSpace = ColorSpace.UNKNOWN
    format: str = ""
    resolution_capped: bool = False
    original_width: int = Field(default=0, ge=0)
    original_height: int = Field(default=0, ge=0)

    @property
    def bytes_estimate(self) -> int:
        """GPU footprint estimate: RGBA at the texture's bit depth."""
        return self.width * self.height * 4 * (self.bit_depth // 8)


class MaterialInfo(BaseModel):
    """One normalized PBR material (content-addressed texture references)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = ""
    pbr_ok: bool = False
    base_color_texture: Optional[str] = None  # content hash
    normal_texture: Optional[str] = None
    roughness_texture: Optional[str] = None
    metallic_texture: Optional[str] = None
    unsupported_extension: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class VramEstimate(BaseModel):
    """Pre-preview VRAM budget estimate (BLOCKED => never rendered)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    geometry_bytes: int = Field(ge=0)
    texture_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    hard_limit_bytes: int = Field(ge=1)
    decision: VramDecision = VramDecision.WITHIN_BUDGET
    detail: str = ""

    @model_validator(mode="before")
    @classmethod
    def _derive_decision(cls, data: Any) -> Any:
        """Derive the decision from the numbers (fail closed on limits)."""
        if not isinstance(data, dict):
            return data
        total = data.get("total_bytes", 0)
        hard_limit = data.get("hard_limit_bytes", 1)
        data = dict(data)
        data["decision"] = (
            VramDecision.WITHIN_BUDGET if total <= hard_limit else VramDecision.BLOCKED
        )
        return data


class LodEntry(BaseModel):
    """One decimated level-of-detail (LOD0 = source, never overwritten)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: int = Field(ge=0)
    triangle_count: int = Field(ge=0)
    vertex_count: int = Field(ge=0)
    ratio: float = Field(default=1.0, gt=0, le=1.0)
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    content_hash: str = Field(min_length=64, max_length=64)
    file_name: str = ""
    local_path: str = ""  # engine-produced file to copy into the bundle
    generated_by: str = ""  # "source" | "blender_job" | "fake"
    metrics: Dict[str, Any] = Field(default_factory=dict)


class PreviewRenderResult(BaseModel):
    """Outcome of the deterministic turntable/thumbnail preview render."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    thumbnail_file: str = ""
    turntable_files: List[str] = Field(default_factory=list)
    frames_rendered: int = Field(default=0, ge=0)
    engine: str = "CYCLES"
    device: str = "CPU"
    profile: PreviewProfile = Field(default_factory=PreviewProfile)
    content_hash: str = ""
    local_files: List[str] = Field(default_factory=list)  # files to copy into the bundle
    generated_by: str = ""  # "blender_job" | "fake"


class BundleFile(BaseModel):
    """One immutable file inside the published asset bundle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = ""
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)


class AssetBundle(BaseModel):
    """Immutable published bundle: interchange + textures + preview + reports."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_id: str = ""
    bundle_hash: str = Field(min_length=64, max_length=64)
    root: str = ""
    files: List[BundleFile] = Field(default_factory=list)

    @staticmethod
    def compute_hash(file_entries: List[BundleFile]) -> str:
        """Deterministic bundle hash over sorted (path, sha256) pairs."""
        canonical = sorted((f.path, f.sha256) for f in file_entries)
        raw = "".join(f"{path}:{digest};" for path, digest in canonical)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NormalizationRequest(BaseModel):
    """One normalization invocation: a trusted, content-addressed asset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    asset: ReferenceAsset
    format: AssetFormat = AssetFormat.UNKNOWN
    config: NormalizationConfig = Field(default_factory=NormalizationConfig)
    requirement: Optional[AssetRequirement] = None
    source_uri: str = ""
    adapter_version: str = "0.0.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NormalizedAsset(BaseModel):
    """Result of a normalization run (status BLOCKED/FAILED carries no bundle)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: NormalizationRunId
    source_content_hash: str = Field(min_length=64, max_length=64)
    format: AssetFormat
    status: NormalizationStatus
    canonical_metadata: CanonicalMetadata = Field(default_factory=CanonicalMetadata)
    mesh_report: MeshValidationReport = Field(default_factory=MeshValidationReport)
    materials: List[MaterialInfo] = Field(default_factory=list)
    textures: List[TextureInfo] = Field(default_factory=list)
    vram: Optional[VramEstimate] = None
    lods: List[LodEntry] = Field(default_factory=list)
    preview: Optional[PreviewRenderResult] = None
    bundle: Optional[AssetBundle] = None
    derived_content_hash: str = ""
    report: NormalizationReport = Field(default_factory=NormalizationReport)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def ready(self) -> bool:
        return self.status == NormalizationStatus.READY


__all__ = [
    "utc_now",
    "DEFAULT_PREVIEW_WIDTH",
    "DEFAULT_PREVIEW_HEIGHT",
    "DEFAULT_PREVIEW_SAMPLES",
    "DEFAULT_PREVIEW_FRAMES",
    "PreviewProfile",
    "NormalizationConfig",
    "StageRecord",
    "NormalizationReport",
    "CanonicalMetadata",
    "MeshValidationReport",
    "TextureInfo",
    "MaterialInfo",
    "VramEstimate",
    "LodEntry",
    "PreviewRenderResult",
    "BundleFile",
    "AssetBundle",
    "NormalizationRequest",
    "NormalizedAsset",
]
