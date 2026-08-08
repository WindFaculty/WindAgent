"""
Asset Normalization pipeline (VP3D Phase 7, Stage C).

Host-side, engine-neutral implementation of the canonical flow:

    ingest -> security -> parse -> unit/axis -> mesh -> material/texture
    -> poly/VRAM budget -> LOD -> preview render -> approval/cache

Engine work (sandboxed import of FBX/USD/BLEND, LOD decimation, deterministic
preview render) is delegated through the injected ``AssetJobRunner`` port;
CI runs the deterministic ``FakeAssetJobRunner``.
"""

from windagent_tools.media_assets.normalization.pipeline import (
    AssetNormalizationPipeline,
    AssetNormalizer,
)
from windagent_tools.media_assets.normalization.job_runner import (
    AssetJobRunner,
    JobInvocation,
    JobResult,
)
from windagent_tools.media_assets.normalization.fakes import FakeAssetJobRunner
from windagent_tools.media_assets.normalization.snapshot import (
    AnimationRef,
    ArmatureRef,
    ImageRef,
    MaterialRef,
    MeshObject,
    MeshPart,
    MeshSnapshot,
)
from windagent_tools.media_assets.normalization.parsers import (
    detect_format,
    parse_asset,
    parse_glb,
    parse_gltf,
    parse_obj,
)

__all__ = [
    "AssetNormalizationPipeline",
    "AssetNormalizer",
    "AssetJobRunner",
    "JobInvocation",
    "JobResult",
    "FakeAssetJobRunner",
    "AnimationRef",
    "ArmatureRef",
    "ImageRef",
    "MaterialRef",
    "MeshObject",
    "MeshPart",
    "MeshSnapshot",
    "detect_format",
    "parse_asset",
    "parse_glb",
    "parse_gltf",
    "parse_obj",
]
