"""
Engine-neutral snapshot of a parsed 3D asset (VP3D Phase 7).

``MeshSnapshot`` is the host-side, engine-agnostic view of a parsed asset —
pure dataclasses, no ``bpy``. It feeds mesh validation, VRAM estimation,
material/texture normalization, LOD planning and bundle publishing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    UnitSystem,
    UpAxis,
)


@dataclass(frozen=True)
class MeshPart:
    """One primitive/mesh part with its own material binding."""

    name: str
    triangle_count: int
    vertex_count: int
    has_uv: bool
    has_normals: bool
    material_index: Optional[int] = None
    mode: int = 4  # glTF primitive mode (4 = TRIANGLES)


@dataclass(frozen=True)
class MeshObject:
    """One mesh object in the asset."""

    name: str
    parts: List[MeshPart] = field(default_factory=list)
    skinned: bool = False

    @property
    def triangle_count(self) -> int:
        return sum(p.triangle_count for p in self.parts)

    @property
    def vertex_count(self) -> int:
        return sum(p.vertex_count for p in self.parts)

    @property
    def has_uv(self) -> bool:
        return all(p.has_uv for p in self.parts)


@dataclass(frozen=True)
class ImageRef:
    """Texture image referenced by a material (may need normalization)."""

    name: str
    mime_type: str = ""
    width: int = 0
    height: int = 0
    bit_depth: int = 8
    color_space: str = "sRGB"
    data: Optional[bytes] = None  # embedded bytes when the source carried them
    external_uri: str = ""        # non-empty when the texture is an external file


@dataclass(frozen=True)
class MaterialRef:
    """Material as declared by the source asset."""

    name: str
    pbr: bool = False
    base_color_texture: Optional[str] = None
    normal_texture: Optional[str] = None
    roughness_texture: Optional[str] = None
    metallic_texture: Optional[str] = None
    unsupported_extension: Optional[str] = None
    missing_textures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnimationRef:
    """One animation clip."""

    name: str
    channels: int = 0


@dataclass(frozen=True)
class ArmatureRef:
    """One skeleton/armature."""

    name: str
    bones: int = 0


@dataclass(frozen=True)
class MeshSnapshot:
    """Neutral view of a parsed asset for the whole pipeline."""

    format: AssetFormat
    objects: List[MeshObject] = field(default_factory=list)
    materials: List[MaterialRef] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    animations: List[AnimationRef] = field(default_factory=list)
    armatures: List[ArmatureRef] = field(default_factory=list)
    unit_hint: Optional[UnitSystem] = None
    up_axis_hint: Optional[UpAxis] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def triangle_count(self) -> int:
        return sum(o.triangle_count for o in self.objects)

    @property
    def vertex_count(self) -> int:
        return sum(o.vertex_count for o in self.objects)

    @property
    def object_count(self) -> int:
        return len(self.objects)


__all__ = ["MeshPart", "MeshObject", "ImageRef", "MaterialRef", "AnimationRef", "ArmatureRef", "MeshSnapshot"]
