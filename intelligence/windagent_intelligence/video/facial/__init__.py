"""Stage I facial pipeline layer (VP3D Phase 18 — Lip-sync / Facial Pipeline)."""

from windagent_intelligence.video.facial.compiler import (
    FACIAL_BINDING_TABLE,
    FACIAL_LAYER_VERSION,
    FacialAnimationCompiler,
    FacialCompileRequest,
)
from windagent_intelligence.video.facial.fake_alignment import (
    LINE_A_PHONEMES,
    LINE_B_PHONEMES,
    VIETNAMESE_LINE_A,
    VIETNAMESE_LINE_B,
    fake_alignment,
)

__all__ = [
    "FACIAL_LAYER_VERSION",
    "FACIAL_BINDING_TABLE",
    "FacialAnimationCompiler",
    "FacialCompileRequest",
    "fake_alignment",
    "VIETNAMESE_LINE_A",
    "VIETNAMESE_LINE_B",
    "LINE_A_PHONEMES",
    "LINE_B_PHONEMES",
]
