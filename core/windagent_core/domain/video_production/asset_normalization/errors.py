"""
Typed errors for asset normalization (VP3D Phase 7, Stage C).

All errors fail closed: a malformed, unsupported, or budget-exceeding asset
raises BEFORE any preview render or publish happens.
"""

from __future__ import annotations


class AssetNormalizationError(RuntimeError):
    """Base error for the normalization pipeline."""

    code = "ASSET_NORMALIZATION_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedFormatError(AssetNormalizationError):
    """The asset format cannot be parsed by this pipeline."""

    code = "ASSET_NORMALIZATION_UNSUPPORTED_FORMAT"


class MalformedAssetError(AssetNormalizationError):
    """The payload parsed but its structure is invalid (fail closed)."""

    code = "ASSET_NORMALIZATION_MALFORMED_ASSET"


class AssetSecurityRejectedError(AssetNormalizationError):
    """The payload failed the static security scan (executable/archive/script)."""

    code = "ASSET_NORMALIZATION_SECURITY_REJECTED"


class VramBudgetExceededError(AssetNormalizationError):
    """VRAM estimate exceeds the hard limit — the pipeline is BLOCKED."""

    code = "ASSET_NORMALIZATION_VRAM_BUDGET_EXCEEDED"


class PolygonBudgetExceededError(AssetNormalizationError):
    """Polygon count exceeds the hard budget — the pipeline is BLOCKED."""

    code = "ASSET_NORMALIZATION_POLYGON_BUDGET_EXCEEDED"


class MeshValidationError(AssetNormalizationError):
    """Blocking mesh defects found (non-manifold / degenerate / topology)."""

    code = "ASSET_NORMALIZATION_MESH_INVALID"


class BlenderJobUnavailableError(AssetNormalizationError):
    """The asset format needs a Blender job but no job runner is available."""

    code = "ASSET_NORMALIZATION_BLENDER_JOB_UNAVAILABLE"


class PreviewRenderError(AssetNormalizationError):
    """Preview render failed; nothing is published."""

    code = "ASSET_NORMALIZATION_PREVIEW_RENDER_FAILED"


class LODGenerationError(AssetNormalizationError):
    """LOD generation failed; nothing is published."""

    code = "ASSET_NORMALIZATION_LOD_GENERATION_FAILED"


class ContentHashMismatchError(AssetNormalizationError):
    """Ingested bytes do not match the declared content hash (fail closed)."""

    code = "ASSET_NORMALIZATION_CONTENT_HASH_MISMATCH"


__all__ = [
    "AssetNormalizationError",
    "UnsupportedFormatError",
    "MalformedAssetError",
    "AssetSecurityRejectedError",
    "VramBudgetExceededError",
    "PolygonBudgetExceededError",
    "MeshValidationError",
    "BlenderJobUnavailableError",
    "PreviewRenderError",
    "LODGenerationError",
    "ContentHashMismatchError",
]
