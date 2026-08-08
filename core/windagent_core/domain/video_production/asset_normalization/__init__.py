"""
Asset Normalization — provider-neutral domain (VP3D Phase 7, Stage C).

Every 3D asset is normalized toward a canonical internal profile (meters,
Z-up, PBR materials, content-addressed textures) BEFORE the Scene Compiler
consumes it. Rules enforced by this domain:

- Canonical metadata is meters + Z-up; adapters are responsible for converting
  the real units/axis they import.
- Hard-limit checks (polygon count, texture resolution, VRAM estimate) fail
  closed BEFORE any preview render: an over-budget asset is ``BLOCKED`` and is
  never blindly rendered.
- LODs are derived artifacts: the source is never overwritten, every LOD has
  its own hash and quality metrics.
- The published asset bundle is immutable: interchange file + textures +
  preview + manifest + provenance + validation report with a deterministic
  bundle hash.
"""

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
from windagent_core.domain.video_production.asset_normalization.errors import (
    AssetNormalizationError,
    AssetSecurityRejectedError,
    BlenderJobUnavailableError,
    ContentHashMismatchError,
    LODGenerationError,
    MalformedAssetError,
    MeshValidationError,
    PolygonBudgetExceededError,
    PreviewRenderError,
    UnsupportedFormatError,
    VramBudgetExceededError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    AssetBundle,
    BundleFile,
    CanonicalMetadata,
    LodEntry,
    MaterialInfo,
    MeshValidationReport,
    NormalizationConfig,
    NormalizationReport,
    NormalizationRequest,
    NormalizedAsset,
    PreviewProfile,
    PreviewRenderResult,
    StageRecord,
    TextureInfo,
    VramEstimate,
)

__all__ = [
    # enums
    "AssetFormat",
    "ColorSpace",
    "LodPolicy",
    "NormalizationStage",
    "NormalizationStatus",
    "StageStatus",
    "UnitSystem",
    "UpAxis",
    "VramDecision",
    # errors
    "AssetNormalizationError",
    "AssetSecurityRejectedError",
    "BlenderJobUnavailableError",
    "ContentHashMismatchError",
    "LODGenerationError",
    "MalformedAssetError",
    "MeshValidationError",
    "PolygonBudgetExceededError",
    "PreviewRenderError",
    "UnsupportedFormatError",
    "VramBudgetExceededError",
    # models
    "AssetBundle",
    "BundleFile",
    "CanonicalMetadata",
    "LodEntry",
    "MaterialInfo",
    "MeshValidationReport",
    "NormalizationConfig",
    "NormalizationReport",
    "NormalizationRequest",
    "NormalizedAsset",
    "PreviewProfile",
    "PreviewRenderResult",
    "StageRecord",
    "TextureInfo",
    "VramEstimate",
]
