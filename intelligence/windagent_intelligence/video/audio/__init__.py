"""
Phase 21 — Dialogue, TTS và audio production (plan 06 §6-§10,
gate VP21_AUDIO_PIPELINE_VERIFIED).

The audio pipeline builds a precise, voice-consistent dialogue/narration
track with word timestamps and a versioned mix plan. It is provider-neutral
(TTS goes through `TtsProviderPort`), fail-closed (invalid TTS output never
publishes, low alignment confidence routes to human, unknown-license cues
block the mix) and fully deterministic/offline except the TTS port.

Workstream (§8): dialogue preparation -> voice casting -> TTS -> forced
alignment -> mix plan.
"""

from windagent_intelligence.video.audio.models import (
    AlignmentReceipt,
    AudioIssue,
    AudioPipelineReceipt,
    DialoguePreparationReceipt,
    TtsSynthesisReceipt,
    VoiceCastReceipt,
)
from windagent_intelligence.video.audio.dialogue import (
    DIALOGUE_PREP_VERSION,
    DialoguePreparer,
    PRONUNCIATION_LEXICON_VERSION,
)
from windagent_intelligence.video.audio.voice import (
    VOICE_CAST_VERSION,
    VoiceCastingService,
)
from windagent_intelligence.video.audio.tts import (
    TTS_PIPELINE_VERSION,
    TtsProviderPort,
    TtsSynthesisRequest,
    TtsSynthesisResult,
    TtsSynthesizer,
)
from windagent_intelligence.video.audio.alignment import (
    ALIGNMENT_VERSION,
    AlignmentService,
)
from windagent_intelligence.video.audio.mix import (
    MIX_VERSION,
    MixPlanner,
)
from windagent_intelligence.video.audio.pipeline import (
    AUDIO_PIPELINE_VERSION,
    AudioPipelineConfig,
    AudioPipelineService,
)

__all__ = [
    # receipts
    "AudioIssue",
    "DialoguePreparationReceipt",
    "VoiceCastReceipt",
    "TtsSynthesisReceipt",
    "AlignmentReceipt",
    "AudioPipelineReceipt",
    # dialogue preparation
    "DIALOGUE_PREP_VERSION",
    "PRONUNCIATION_LEXICON_VERSION",
    "DialoguePreparer",
    # voice casting
    "VOICE_CAST_VERSION",
    "VoiceCastingService",
    # TTS
    "TTS_PIPELINE_VERSION",
    "TtsProviderPort",
    "TtsSynthesisRequest",
    "TtsSynthesisResult",
    "TtsSynthesizer",
    # alignment
    "ALIGNMENT_VERSION",
    "AlignmentService",
    # mix
    "MIX_VERSION",
    "MixPlanner",
    # pipeline
    "AUDIO_PIPELINE_VERSION",
    "AudioPipelineConfig",
    "AudioPipelineService",
]
