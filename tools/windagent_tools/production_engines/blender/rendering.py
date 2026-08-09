"""VP3D Phase 19 - versioned Cycles production-render contracts.

This module is the Blender adapter boundary for the engine-neutral
``RenderIntent``.  It deliberately contains no ``bpy`` import: profile
compilation, device policy, cache identity, and telemetry parsing stay fully
testable outside Blender.  The trusted ``execute_job.py`` script consumes the
serialized profile and is the only layer that touches Blender data blocks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional

from windagent_core.domain.video_production.production_ir.models import RenderIntent
from windagent_tools.production_engines.blender.runtime.capabilities import (
    BlenderCapabilityReport,
)

RENDER_PROFILE_SCHEMA_VERSION = "1.0.0"
RENDER_SETTINGS_VERSION = "cycles-production-1.0.0"
POST_PRODUCTION_CONTRACT_VERSION = "image-sequence-1.0.0"
RENDER_CACHE_SCHEMA_VERSION = "render-cache-1.0.0"

PROFILE_PREVIEW = "PREVIEW"
PROFILE_FINAL = "FINAL"
PROFILE_FINAL_HIGH = "FINAL_HIGH"
PROFILE_NAMES = (PROFILE_PREVIEW, PROFILE_FINAL, PROFILE_FINAL_HIGH)

ARTIFACT_CLASS_PREVIEW = "PREVIEW"
ARTIFACT_CLASS_FINAL = "FINAL"

ENGINE_CYCLES = "CYCLES"

DEVICE_AUTO = "AUTO"
DEVICE_OPTIX = "OPTIX"
DEVICE_CUDA = "CUDA"
DEVICE_CPU = "CPU"
DEVICE_CLASSES = (DEVICE_OPTIX, DEVICE_CUDA, DEVICE_CPU)

CPU_FALLBACK_DENY = "DENY"
CPU_FALLBACK_ALLOW = "ALLOW"
CPU_FALLBACK_POLICIES = (CPU_FALLBACK_DENY, CPU_FALLBACK_ALLOW)

DEVICE_VERDICT_GPU_SELECTED = "GPU_SELECTED"
DEVICE_VERDICT_EXPLICIT_CPU = "EXPLICIT_CPU"
DEVICE_VERDICT_CPU_FALLBACK_APPROVED = "CPU_FALLBACK_APPROVED"

OUTPUT_PNG = "PNG"
OUTPUT_EXR = "OPEN_EXR"
OUTPUT_FORMATS = (OUTPUT_PNG, OUTPUT_EXR)


class RenderProfileCompileError(ValueError):
    """The neutral intent cannot be compiled to a safe Blender profile."""


class RenderDevicePolicyError(RuntimeError):
    """The requested Cycles device cannot be selected under current policy."""


class RenderArtifactPromotionError(RuntimeError):
    """An artifact was promoted across incompatible render classes."""


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalise_hashes(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        if str(key) and str(item)
    }


def _output_format(value: Any) -> str:
    raw = getattr(value, "value", value)
    name = str(raw or "").upper()
    if name in ("EXR", "OPEN_EXR"):
        return OUTPUT_EXR
    if name == OUTPUT_PNG:
        return OUTPUT_PNG
    raise RenderProfileCompileError(
        f"unsupported production image-sequence format {raw!r}; expected PNG or EXR"
    )


@dataclass(frozen=True)
class ColorManagementSettings:
    """Pinned film and view-transform settings."""

    view_transform: str = "AgX"
    look: str = "Medium High Contrast"
    exposure: float = 0.0
    gamma: float = 1.0
    film_transparent: bool = False

    def to_dict(self) -> dict:
        return {
            "view_transform": self.view_transform,
            "look": self.look,
            "exposure": self.exposure,
            "gamma": self.gamma,
            "film_transparent": self.film_transparent,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ColorManagementSettings":
        return cls(
            view_transform=str(data.get("view_transform", "AgX")),
            look=str(data.get("look", "Medium High Contrast")),
            exposure=float(data.get("exposure", 0.0)),
            gamma=float(data.get("gamma", 1.0)),
            film_transparent=bool(data.get("film_transparent", False)),
        )


@dataclass(frozen=True)
class CyclesBounceBudget:
    """Bounded Cycles path-tracing bounce configuration."""

    max_bounces: int
    diffuse_bounces: int
    glossy_bounces: int
    transmission_bounces: int
    volume_bounces: int
    transparent_bounces: int

    def to_dict(self) -> dict:
        return {
            "max_bounces": self.max_bounces,
            "diffuse_bounces": self.diffuse_bounces,
            "glossy_bounces": self.glossy_bounces,
            "transmission_bounces": self.transmission_bounces,
            "volume_bounces": self.volume_bounces,
            "transparent_bounces": self.transparent_bounces,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CyclesBounceBudget":
        return cls(
            max_bounces=int(data.get("max_bounces", 0)),
            diffuse_bounces=int(data.get("diffuse_bounces", 0)),
            glossy_bounces=int(data.get("glossy_bounces", 0)),
            transmission_bounces=int(data.get("transmission_bounces", 0)),
            volume_bounces=int(data.get("volume_bounces", 0)),
            transparent_bounces=int(data.get("transparent_bounces", 0)),
        )


@dataclass(frozen=True)
class RenderResourceLimits:
    """Quality-tier limits consumed by scene preparation and Blender simplify."""

    texture_limit_px: int
    geometry_limit_vertices: int
    max_subdivision_level: int
    lod_policy: str

    def to_dict(self) -> dict:
        return {
            "texture_limit_px": self.texture_limit_px,
            "geometry_limit_vertices": self.geometry_limit_vertices,
            "max_subdivision_level": self.max_subdivision_level,
            "lod_policy": self.lod_policy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderResourceLimits":
        return cls(
            texture_limit_px=int(data.get("texture_limit_px", 0)),
            geometry_limit_vertices=int(data.get("geometry_limit_vertices", 0)),
            max_subdivision_level=int(data.get("max_subdivision_level", 0)),
            lod_policy=str(data.get("lod_policy", "")),
        )


@dataclass(frozen=True)
class BlenderRenderProfile:
    """Fully resolved, versioned Blender/Cycles render settings."""

    name: str
    artifact_class: str
    engine: str
    device: str
    resolution: Dict[str, int]
    fps: int
    samples: int
    adaptive_sampling: bool
    adaptive_threshold: float
    denoise: bool
    bounce_budget: CyclesBounceBudget
    motion_blur: bool
    motion_blur_shutter: float
    persistent_data: bool
    persistent_data_evidence_hash: str
    use_instancing: bool
    use_spatial_splits: bool
    resource_limits: RenderResourceLimits
    color_management: ColorManagementSettings
    output_format: str
    output_color_depth: str
    output_compression: int
    seed: int
    dependency_hashes: Dict[str, str] = field(default_factory=dict)
    schema_version: str = RENDER_PROFILE_SCHEMA_VERSION
    settings_version: str = RENDER_SETTINGS_VERSION
    post_production_contract_version: str = POST_PRODUCTION_CONTRACT_VERSION

    @property
    def extension(self) -> str:
        return "exr" if self.output_format == OUTPUT_EXR else "png"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "settings_version": self.settings_version,
            "post_production_contract_version": self.post_production_contract_version,
            "name": self.name,
            "artifact_class": self.artifact_class,
            "engine": self.engine,
            "device": self.device,
            "resolution": dict(self.resolution),
            "fps": self.fps,
            "samples": self.samples,
            "adaptive_sampling": self.adaptive_sampling,
            "adaptive_threshold": self.adaptive_threshold,
            "denoise": self.denoise,
            "bounce_budget": self.bounce_budget.to_dict(),
            "motion_blur": self.motion_blur,
            "motion_blur_shutter": self.motion_blur_shutter,
            "persistent_data": self.persistent_data,
            "persistent_data_evidence_hash": self.persistent_data_evidence_hash,
            "use_instancing": self.use_instancing,
            "use_spatial_splits": self.use_spatial_splits,
            "resource_limits": self.resource_limits.to_dict(),
            "color_management": self.color_management.to_dict(),
            "output_format": self.output_format,
            "output_color_depth": self.output_color_depth,
            "output_compression": self.output_compression,
            "seed": self.seed,
            "dependency_hashes": dict(self.dependency_hashes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlenderRenderProfile":
        """Deserialize the exact JSON contract consumed by Blender."""
        return cls(
            schema_version=str(data.get("schema_version", RENDER_PROFILE_SCHEMA_VERSION)),
            settings_version=str(data.get("settings_version", RENDER_SETTINGS_VERSION)),
            post_production_contract_version=str(
                data.get(
                    "post_production_contract_version",
                    POST_PRODUCTION_CONTRACT_VERSION,
                )
            ),
            name=str(data.get("name", "")),
            artifact_class=str(data.get("artifact_class", "")),
            engine=str(data.get("engine", "")),
            device=str(data.get("device", "")),
            resolution={
                "width": int((data.get("resolution") or {}).get("width", 0)),
                "height": int((data.get("resolution") or {}).get("height", 0)),
            },
            fps=int(data.get("fps", 0)),
            samples=int(data.get("samples", 0)),
            adaptive_sampling=bool(data.get("adaptive_sampling", False)),
            adaptive_threshold=float(data.get("adaptive_threshold", 0.0)),
            denoise=bool(data.get("denoise", False)),
            bounce_budget=CyclesBounceBudget.from_dict(data.get("bounce_budget") or {}),
            motion_blur=bool(data.get("motion_blur", False)),
            motion_blur_shutter=float(data.get("motion_blur_shutter", 0.0)),
            persistent_data=bool(data.get("persistent_data", False)),
            persistent_data_evidence_hash=str(
                data.get("persistent_data_evidence_hash", "")
            ),
            use_instancing=bool(data.get("use_instancing", False)),
            use_spatial_splits=bool(data.get("use_spatial_splits", False)),
            resource_limits=RenderResourceLimits.from_dict(
                data.get("resource_limits") or {}
            ),
            color_management=ColorManagementSettings.from_dict(
                data.get("color_management") or {}
            ),
            output_format=str(data.get("output_format", "")),
            output_color_depth=str(data.get("output_color_depth", "")),
            output_compression=int(data.get("output_compression", 0)),
            seed=int(data.get("seed", 0)),
            dependency_hashes=_normalise_hashes(data.get("dependency_hashes")),
        )

    def profile_hash(self) -> str:
        return _canonical_hash(self.to_dict())


def _profile_catalog() -> Dict[str, BlenderRenderProfile]:
    """Return fresh immutable profile objects so callers cannot mutate a catalog."""
    common = {
        "engine": ENGINE_CYCLES,
        "device": DEVICE_AUTO,
        "adaptive_sampling": True,
        "denoise": True,
        "persistent_data": False,
        "persistent_data_evidence_hash": "",
        "use_instancing": True,
        "color_management": ColorManagementSettings(),
        "seed": 0,
    }
    return {
        PROFILE_PREVIEW: BlenderRenderProfile(
            name=PROFILE_PREVIEW,
            artifact_class=ARTIFACT_CLASS_PREVIEW,
            resolution={"width": 1280, "height": 720},
            fps=24,
            samples=32,
            adaptive_threshold=0.10,
            bounce_budget=CyclesBounceBudget(4, 2, 2, 4, 0, 4),
            motion_blur=False,
            motion_blur_shutter=0.0,
            use_spatial_splits=False,
            resource_limits=RenderResourceLimits(2048, 8_000_000, 1, "PREVIEW"),
            output_format=OUTPUT_PNG,
            output_color_depth="8",
            output_compression=30,
            **common,
        ),
        PROFILE_FINAL: BlenderRenderProfile(
            name=PROFILE_FINAL,
            artifact_class=ARTIFACT_CLASS_FINAL,
            resolution={"width": 1920, "height": 1080},
            fps=24,
            samples=128,
            adaptive_threshold=0.03,
            bounce_budget=CyclesBounceBudget(12, 4, 4, 8, 2, 8),
            motion_blur=True,
            motion_blur_shutter=0.5,
            use_spatial_splits=True,
            resource_limits=RenderResourceLimits(4096, 25_000_000, 2, "FINAL"),
            output_format=OUTPUT_EXR,
            output_color_depth="16",
            output_compression=15,
            **common,
        ),
        PROFILE_FINAL_HIGH: BlenderRenderProfile(
            name=PROFILE_FINAL_HIGH,
            artifact_class=ARTIFACT_CLASS_FINAL,
            resolution={"width": 3840, "height": 2160},
            fps=24,
            samples=256,
            adaptive_threshold=0.01,
            bounce_budget=CyclesBounceBudget(16, 6, 6, 12, 4, 12),
            motion_blur=True,
            motion_blur_shutter=0.5,
            use_spatial_splits=True,
            resource_limits=RenderResourceLimits(8192, 50_000_000, 3, "FINAL_HIGH"),
            output_format=OUTPUT_EXR,
            output_color_depth="16",
            output_compression=10,
            **common,
        ),
    }


class BlenderRenderProfileCatalog:
    """Versioned built-in PREVIEW/FINAL/FINAL_HIGH settings."""

    version = RENDER_SETTINGS_VERSION

    @staticmethod
    def names() -> tuple[str, ...]:
        return PROFILE_NAMES

    def get(self, name: str) -> BlenderRenderProfile:
        key = str(name).upper()
        try:
            return _profile_catalog()[key]
        except KeyError as exc:
            raise RenderProfileCompileError(
                f"unknown Blender render profile {name!r}; expected one of {PROFILE_NAMES}"
            ) from exc


def _intent_profile_name(intent: RenderIntent) -> str:
    metadata_name = str(intent.profile.metadata.get("blender_profile", "")).upper()
    if metadata_name:
        return metadata_name
    profile_id = str(intent.profile.profile_id).upper()
    for name in PROFILE_NAMES:
        if profile_id == name or profile_id.endswith(f"_{name}"):
            return name
    quality = str(getattr(intent.profile.quality, "value", intent.profile.quality)).upper()
    return {
        "DRAFT": PROFILE_PREVIEW,
        "PREVIEW": PROFILE_PREVIEW,
        "HIGH": PROFILE_FINAL_HIGH,
        "FINAL": PROFILE_FINAL,
    }.get(quality, PROFILE_FINAL)


class BlenderRenderProfileCompiler:
    """Compile an engine-neutral ``RenderIntent`` inside the Blender adapter."""

    compiler_version = "blender-render-profile-1.0.0"

    def __init__(self, catalog: Optional[BlenderRenderProfileCatalog] = None) -> None:
        self._catalog = catalog or BlenderRenderProfileCatalog()

    def compile(
        self,
        intent: RenderIntent,
        *,
        device: str,
        dependency_hashes: Optional[Mapping[str, str]] = None,
    ) -> BlenderRenderProfile:
        engine_hint = str(intent.profile.engine_hint or "").strip().upper()
        if engine_hint and engine_hint != ENGINE_CYCLES:
            raise RenderProfileCompileError(
                f"engine hint {engine_hint!r} is not permitted by the Cycles profile; "
                "WindAgent never silently switches to Eevee"
            )
        selected_device = str(device).upper()
        if selected_device not in DEVICE_CLASSES:
            raise RenderProfileCompileError(
                f"compiled profile requires an actual device class, got {device!r}"
            )

        base = self._catalog.get(_intent_profile_name(intent))
        metadata = intent.profile.metadata
        resolution = dict(intent.profile.resolution or base.resolution)
        width = int(resolution.get("width", 0))
        height = int(resolution.get("height", 0))
        if width <= 0 or height <= 0:
            raise RenderProfileCompileError("render resolution must be positive")

        # Persistent data is only enabled when a measurement receipt is pinned.
        persistent_evidence = str(metadata.get("persistent_data_evidence_hash", ""))
        persistent_data = bool(metadata.get("persistent_data", False))
        if persistent_data and not persistent_evidence:
            raise RenderProfileCompileError(
                "persistent_data requires persistent_data_evidence_hash from a measured benefit"
            )

        color = ColorManagementSettings(
            view_transform=str(metadata.get("view_transform", "AgX")),
            look=str(metadata.get("look", "Medium High Contrast")),
            exposure=float(metadata.get("exposure", 0.0)),
            gamma=float(metadata.get("gamma", 1.0)),
            film_transparent=bool(metadata.get("film_transparent", False)),
        )
        seed = metadata.get("seed")
        if seed is None:
            seed = int(_canonical_hash(intent.model_dump(mode="json"))[:8], 16)

        hashes = _normalise_hashes(dependency_hashes)
        hashes.update(_normalise_hashes(metadata.get("dependency_hashes")))
        output_format = _output_format(intent.profile.output_format)
        output_depth = "16" if output_format == OUTPUT_EXR else "8"
        adaptive_threshold = float(
            metadata.get("adaptive_threshold", base.adaptive_threshold)
        )
        if adaptive_threshold < 0.0 or adaptive_threshold > 1.0:
            raise RenderProfileCompileError("adaptive_threshold must be between 0 and 1")
        output_compression = int(
            metadata.get("output_compression", base.output_compression)
        )
        if output_compression < 0 or output_compression > 100:
            raise RenderProfileCompileError("output_compression must be between 0 and 100")
        motion_blur_shutter = float(
            metadata.get("motion_blur_shutter", base.motion_blur_shutter)
        )
        if motion_blur_shutter < 0.0 or motion_blur_shutter > 1.0:
            raise RenderProfileCompileError("motion_blur_shutter must be between 0 and 1")

        return replace(
            base,
            device=selected_device,
            resolution={"width": width, "height": height},
            fps=int(intent.profile.frame_rate),
            samples=int(intent.profile.samples),
            adaptive_sampling=bool(intent.profile.adaptive_sampling),
            adaptive_threshold=adaptive_threshold,
            denoise=bool(intent.profile.denoise),
            motion_blur=bool(metadata.get("motion_blur", base.motion_blur)),
            motion_blur_shutter=motion_blur_shutter,
            persistent_data=persistent_data,
            persistent_data_evidence_hash=persistent_evidence,
            color_management=color,
            output_format=output_format,
            output_color_depth=str(metadata.get("output_color_depth", output_depth)),
            output_compression=output_compression,
            seed=int(seed),
            dependency_hashes=hashes,
        )


@dataclass(frozen=True)
class BlenderDeviceSelection:
    """Auditable result of resolving requested vs available Cycles devices."""

    requested_device: str
    selected_device: str
    device_names: List[str]
    fallback_policy: str
    fallback_used: bool
    verdict: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "device_names": list(self.device_names),
            "fallback_policy": self.fallback_policy,
            "fallback_used": self.fallback_used,
            "verdict": self.verdict,
            "reason": self.reason,
        }


class BlenderCyclesDeviceSelector:
    """Resolve OptiX/CUDA/CPU with explicit, fail-closed CPU fallback."""

    def select(
        self,
        report: BlenderCapabilityReport,
        *,
        requested_device: str = DEVICE_AUTO,
        cpu_fallback_policy: str = CPU_FALLBACK_DENY,
    ) -> BlenderDeviceSelection:
        if not report.parsed_ok:
            raise RenderDevicePolicyError(
                f"cannot select Cycles device: capability probe failed: {report.probe_error}"
            )
        requested = str(requested_device or DEVICE_AUTO).upper()
        fallback = str(cpu_fallback_policy or CPU_FALLBACK_DENY).upper()
        if requested not in (DEVICE_AUTO, *DEVICE_CLASSES):
            raise RenderDevicePolicyError(f"unknown requested device {requested!r}")
        if fallback not in CPU_FALLBACK_POLICIES:
            raise RenderDevicePolicyError(f"unknown CPU fallback policy {fallback!r}")

        devices_by_type: Dict[str, List[str]] = {}
        for item in report.cycles_devices:
            kind = item.device_type.upper()
            devices_by_type.setdefault(kind, []).append(item.name)

        if requested == DEVICE_CPU:
            return BlenderDeviceSelection(
                requested, DEVICE_CPU, devices_by_type.get(DEVICE_CPU, ["CPU"]),
                fallback, False, DEVICE_VERDICT_EXPLICIT_CPU,
                "CPU was explicitly requested by render policy",
            )

        candidates: Iterable[str]
        if requested == DEVICE_AUTO:
            candidates = (DEVICE_OPTIX, DEVICE_CUDA)
        else:
            candidates = (requested,)
        for candidate in candidates:
            names = devices_by_type.get(candidate, [])
            if names:
                return BlenderDeviceSelection(
                    requested, candidate, names, fallback, False,
                    DEVICE_VERDICT_GPU_SELECTED,
                    f"Cycles enumerated {len(names)} active {candidate} device(s)",
                )

        if fallback == CPU_FALLBACK_ALLOW:
            return BlenderDeviceSelection(
                requested, DEVICE_CPU, devices_by_type.get(DEVICE_CPU, ["CPU"]),
                fallback, True, DEVICE_VERDICT_CPU_FALLBACK_APPROVED,
                f"{requested} unavailable; explicit policy approved CPU fallback",
            )
        raise RenderDevicePolicyError(
            f"{requested} unavailable and CPU fallback policy is {CPU_FALLBACK_DENY}; "
            "render blocked before launch"
        )


def build_render_cache_key(
    *,
    scene_hash: str,
    shot_hash: str,
    frame_start: int,
    frame_end: int,
    profile: BlenderRenderProfile,
    blender_version: str,
    device_class: str,
) -> str:
    """Cache key covering every Phase 19 render-identity dimension."""
    payload = {
        "schema_version": RENDER_CACHE_SCHEMA_VERSION,
        "scene_hash": str(scene_hash),
        "shot_hash": str(shot_hash),
        "frame_start": int(frame_start),
        "frame_end": int(frame_end),
        "profile_hash": profile.profile_hash(),
        "artifact_class": profile.artifact_class,
        "blender_version": str(blender_version),
        "device_class": str(device_class).upper(),
        "dependency_hashes": dict(profile.dependency_hashes),
    }
    return f"{RENDER_CACHE_SCHEMA_VERSION}:{_canonical_hash(payload)}"


def ensure_artifact_promotion_allowed(
    source_profile: BlenderRenderProfile,
    target_profile: BlenderRenderProfile,
) -> None:
    """Forbid metadata-only PREVIEW -> FINAL promotion."""
    if (
        source_profile.artifact_class == ARTIFACT_CLASS_PREVIEW
        and target_profile.artifact_class == ARTIFACT_CLASS_FINAL
    ):
        raise RenderArtifactPromotionError(
            "preview image sequences cannot be promoted to final; a FINAL render is required"
        )
    if source_profile.profile_hash() != target_profile.profile_hash():
        raise RenderArtifactPromotionError(
            "render profile identity changed; cached artifacts cannot be relabelled"
        )


@dataclass(frozen=True)
class FrameRenderTelemetry:
    frame: int
    render_seconds: float
    samples: int
    peak_memory_mb: Optional[float]
    device: str
    failure: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FrameRenderTelemetry":
        peak = data.get("peak_memory_mb")
        return cls(
            frame=int(data.get("frame", 0)),
            render_seconds=float(data.get("render_seconds", 0.0)),
            samples=int(data.get("samples", 0)),
            peak_memory_mb=None if peak is None else float(peak),
            device=str(data.get("device", "")),
            failure=str(data.get("failure", "")),
        )

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "render_seconds": self.render_seconds,
            "samples": self.samples,
            "peak_memory_mb": self.peak_memory_mb,
            "device": self.device,
            "failure": self.failure,
        }


@dataclass(frozen=True)
class ChunkRenderTelemetry:
    frame_start: int
    frame_end: int
    render_seconds: float
    requested_device: str
    actual_device: str
    profile_hash: str
    cache_key: str
    frames: List[FrameRenderTelemetry] = field(default_factory=list)
    peak_memory_mb: Optional[float] = None
    failure: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChunkRenderTelemetry":
        peak = data.get("peak_memory_mb")
        return cls(
            frame_start=int(data.get("frame_start", 0)),
            frame_end=int(data.get("frame_end", 0)),
            render_seconds=float(data.get("render_seconds", 0.0)),
            requested_device=str(data.get("requested_device", "")),
            actual_device=str(data.get("actual_device", "")),
            profile_hash=str(data.get("profile_hash", "")),
            cache_key=str(data.get("cache_key", "")),
            frames=[
                FrameRenderTelemetry.from_dict(item)
                for item in data.get("frames", []) or []
                if isinstance(item, Mapping)
            ],
            peak_memory_mb=None if peak is None else float(peak),
            failure=str(data.get("failure", "")),
        )

    def to_dict(self) -> dict:
        return {
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "render_seconds": self.render_seconds,
            "requested_device": self.requested_device,
            "actual_device": self.actual_device,
            "profile_hash": self.profile_hash,
            "cache_key": self.cache_key,
            "frames": [item.to_dict() for item in self.frames],
            "peak_memory_mb": self.peak_memory_mb,
            "failure": self.failure,
        }


__all__ = [
    "RENDER_PROFILE_SCHEMA_VERSION",
    "RENDER_SETTINGS_VERSION",
    "POST_PRODUCTION_CONTRACT_VERSION",
    "RENDER_CACHE_SCHEMA_VERSION",
    "PROFILE_PREVIEW",
    "PROFILE_FINAL",
    "PROFILE_FINAL_HIGH",
    "PROFILE_NAMES",
    "ARTIFACT_CLASS_PREVIEW",
    "ARTIFACT_CLASS_FINAL",
    "ENGINE_CYCLES",
    "DEVICE_AUTO",
    "DEVICE_OPTIX",
    "DEVICE_CUDA",
    "DEVICE_CPU",
    "CPU_FALLBACK_DENY",
    "CPU_FALLBACK_ALLOW",
    "DEVICE_VERDICT_GPU_SELECTED",
    "DEVICE_VERDICT_EXPLICIT_CPU",
    "DEVICE_VERDICT_CPU_FALLBACK_APPROVED",
    "OUTPUT_PNG",
    "OUTPUT_EXR",
    "RenderProfileCompileError",
    "RenderDevicePolicyError",
    "RenderArtifactPromotionError",
    "ColorManagementSettings",
    "CyclesBounceBudget",
    "RenderResourceLimits",
    "BlenderRenderProfile",
    "BlenderRenderProfileCatalog",
    "BlenderRenderProfileCompiler",
    "BlenderDeviceSelection",
    "BlenderCyclesDeviceSelector",
    "build_render_cache_key",
    "ensure_artifact_promotion_allowed",
    "FrameRenderTelemetry",
    "ChunkRenderTelemetry",
]
