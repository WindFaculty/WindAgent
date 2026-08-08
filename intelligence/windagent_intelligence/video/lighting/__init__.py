"""Stage G lighting system layer (VP3D Phase 14)."""

from windagent_intelligence.video.lighting.contact_sheet import (
    HISTOGRAM_BINS,
    ContactSheetBuilder,
    ContactSheetEntry,
    LightingContactSheetManifest,
)
from windagent_intelligence.video.lighting.lighting_compiler import (
    LIGHTING_COMPILER_LAYER_VERSION,
    LightingCompileReceipt,
    LightingCompiler,
)
from windagent_intelligence.video.lighting.presets import (
    PRESET_REGISTRY_VERSION,
    all_presets,
    get_preset,
    select_preset,
    supported_preset_ids,
)

__all__ = [
    "HISTOGRAM_BINS",
    "ContactSheetBuilder",
    "ContactSheetEntry",
    "LightingContactSheetManifest",
    "LIGHTING_COMPILER_LAYER_VERSION",
    "LightingCompileReceipt",
    "LightingCompiler",
    "PRESET_REGISTRY_VERSION",
    "all_presets",
    "get_preset",
    "select_preset",
    "supported_preset_ids",
]
