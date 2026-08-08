"""
Canonical enums for asset normalization (VP3D Phase 7, Stage C).

Values are stable string identifiers — never display names — and must not
change once used in receipts. Every asset is normalized toward the canonical
metadata profile (meters, Z-up) before the Scene Compiler consumes it; the
adapters are responsible for converting the actual units/axis they import.
"""

from __future__ import annotations

from enum import Enum


class AssetFormat(str, Enum):
    """Interchange format of a 3D asset.

    ``BLEND`` is ALWAYS a derived artifact and is never an accepted ingest
    format (a source asset cannot arrive as a .blend).
    """

    GLTF = "GLTF"
    GLB = "GLB"
    OBJ = "OBJ"
    FBX = "FBX"
    USD = "USD"
    BLEND = "BLEND"
    UNKNOWN = "UNKNOWN"


class UnitSystem(str, Enum):
    """Unit system of a scene, always normalized to METERS."""

    METERS = "METERS"
    CENTIMETERS = "CENTIMETERS"
    FEET = "FEET"
    INCHES = "INCHES"
    UNKNOWN = "UNKNOWN"

    @property
    def meters_per_unit(self) -> float:
        """Scale factor to convert one unit of this system to meters."""
        return {
            UnitSystem.METERS: 1.0,
            UnitSystem.CENTIMETERS: 0.01,
            UnitSystem.FEET: 0.3048,
            UnitSystem.INCHES: 0.0254,
            UnitSystem.UNKNOWN: 1.0,
        }[self]


class UpAxis(str, Enum):
    """Up axis of a scene, always normalized to Z_UP."""

    Z_UP = "Z_UP"
    Y_UP = "Y_UP"
    X_UP = "X_UP"
    NEG_Z_UP = "NEG_Z_UP"
    NEG_Y_UP = "NEG_Y_UP"
    NEG_X_UP = "NEG_X_UP"
    UNKNOWN = "UNKNOWN"


class ColorSpace(str, Enum):
    """Color space metadata of a normalized texture."""

    SRGB = "sRGB"
    LINEAR = "Linear"
    RAW = "Raw"
    UNKNOWN = "Unknown"


class LodPolicy(str, Enum):
    """LOD generation policy (decimation strategy)."""

    NONE = "NONE"            # keep source geometry only
    SINGLE = "SINGLE"        # one decimated level (LOD1)
    MULTI = "MULTI"          # decimated levels down to a minimum triangle ratio


class VramDecision(str, Enum):
    """Outcome of the pre-preview VRAM budget check."""

    WITHIN_BUDGET = "WITHIN_BUDGET"
    BLOCKED = "BLOCKED"


class NormalizationStage(str, Enum):
    """Pipeline stages of the canonical normalization flow."""

    INGEST = "INGEST"
    SECURITY = "SECURITY"
    PARSE = "PARSE"
    UNIT_AXIS = "UNIT_AXIS"
    MESH = "MESH"
    MATERIAL_TEXTURE = "MATERIAL_TEXTURE"
    BUDGET = "BUDGET"
    LOD = "LOD"
    PREVIEW = "PREVIEW"
    PUBLISH = "PUBLISH"


class NormalizationStatus(str, Enum):
    """Overall outcome of a normalization run.

    ``BLOCKED`` means a hard limit (VRAM/polygon/security) stopped the
    pipeline BEFORE any preview render or publish — a blocked asset is never
    blindly rendered.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class StageStatus(str, Enum):
    """Outcome of one pipeline stage."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


__all__ = [
    "AssetFormat",
    "UnitSystem",
    "UpAxis",
    "ColorSpace",
    "LodPolicy",
    "VramDecision",
    "NormalizationStage",
    "NormalizationStatus",
    "StageStatus",
]
