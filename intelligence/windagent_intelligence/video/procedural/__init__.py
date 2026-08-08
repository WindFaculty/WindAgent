"""Stage H procedural animation layer (VP3D Phase 16 — Procedural Animation)."""

from windagent_intelligence.video.procedural.baker import BakeService
from windagent_intelligence.video.procedural.layers import (
    PROCEDURAL_LAYER_REGISTRY_VERSION,
    default_priority,
    input_defaults,
    ownership,
    requires_anchor,
    supported_layer_kinds,
)
from windagent_intelligence.video.procedural.procedural_compiler import (
    PROCEDURAL_COMPILER_LAYER_VERSION,
    ProceduralBakeReceipt,
    ProceduralCompiler,
)

__all__ = [
    "PROCEDURAL_COMPILER_LAYER_VERSION",
    "PROCEDURAL_LAYER_REGISTRY_VERSION",
    "ProceduralBakeReceipt",
    "ProceduralCompiler",
    "BakeService",
    "default_priority",
    "input_defaults",
    "ownership",
    "requires_anchor",
    "supported_layer_kinds",
]
