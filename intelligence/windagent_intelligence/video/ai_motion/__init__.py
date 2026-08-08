"""Stage H AI motion adapter layer (VP3D Phase 17 — AI Motion Adapter)."""

from windagent_intelligence.video.ai_motion.adapter import (
    MOTION_ADAPTER_LAYER_VERSION,
    TRACK_PROVENANCE_FIELDS,
    AiMotionAdapter,
    MotionApproveReceipt,
)
from windagent_intelligence.video.ai_motion.fake_adapter import (
    FAKE_MODEL,
    FAKE_MODEL_VERSION,
    FAKE_PROVIDER,
    FAKE_SKELETON,
    FakeMotionAdapter,
)
from windagent_intelligence.video.ai_motion.ports import (
    MotionGenerationPort,
    TextToMotionPort,
    TransientProviderError,
    VideoToMotionPort,
)
from windagent_intelligence.video.ai_motion.remap import (
    REQUIRED_TARGET_BONES,
    SkeletonRemapService,
)

__all__ = [
    "MOTION_ADAPTER_LAYER_VERSION",
    "TRACK_PROVENANCE_FIELDS",
    "AiMotionAdapter",
    "MotionApproveReceipt",
    "FakeMotionAdapter",
    "FAKE_PROVIDER",
    "FAKE_MODEL",
    "FAKE_MODEL_VERSION",
    "FAKE_SKELETON",
    "MotionGenerationPort",
    "TextToMotionPort",
    "VideoToMotionPort",
    "TransientProviderError",
    "REQUIRED_TARGET_BONES",
    "SkeletonRemapService",
]
