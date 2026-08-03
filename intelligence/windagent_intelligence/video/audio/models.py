"""
Phase 21 — audio pipeline result types (plan 06 §8, gate
VP21_AUDIO_PIPELINE_VERIFIED).

`AudioPipelineReceipt` is the immutable result of `AudioPipelineService.run`:
the prepared dialogue tracks, the voice cast, the TTS assets (content hashed),
the forced-alignment results and the final versioned mix plan. The receipt
never hides an alignment/timing defect — blocking issues are surfaced as
typed findings that must be resolved (or audited) before the mix publishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.audio import (
    AudioMixPlan,
    CharacterVoiceProfile,
    DialogueTrack,
    TtsAudioAsset,
)


@dataclass(frozen=True)
class AudioIssue:
    """A typed audio-pipeline finding (fail closed, never silently fixed)."""

    code: str
    message: str
    dialogue_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "dialogue_id": self.dialogue_id,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class DialoguePreparationReceipt:
    """Output of dialogue preparation (§8.1)."""

    tracks: List[DialogueTrack]
    issues: List[AudioIssue] = field(default_factory=list)
    lexicon_version: str = ""
    language: str = "vi-VN"
    locale: str = "vi-VN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracks": [t.to_dict() for t in self.tracks],
            "issues": [i.to_dict() for i in self.issues],
            "lexicon_version": self.lexicon_version,
            "language": self.language,
            "locale": self.locale,
        }


@dataclass(frozen=True)
class VoiceCastReceipt:
    """Output of voice casting (§8.2)."""

    profiles: List[CharacterVoiceProfile]
    issues: List[AudioIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profiles": [p.to_dict() for p in self.profiles],
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass(frozen=True)
class TtsSynthesisReceipt:
    """Output of TTS synthesis (§8.3) — every asset content-hashed + validated."""

    assets: List[TtsAudioAsset]
    issues: List[AudioIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assets": [a.to_dict() for a in self.assets],
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass(frozen=True)
class AlignmentReceipt:
    """Output of forced alignment (§8.4) — timing issues never hidden."""

    tracks: List[DialogueTrack]
    issues: List[AudioIssue] = field(default_factory=list)
    timing_proposals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracks": [t.to_dict() for t in self.tracks],
            "issues": [i.to_dict() for i in self.issues],
            "timing_proposals": list(self.timing_proposals),
        }


@dataclass(frozen=True)
class AudioPipelineReceipt:
    """Immutable result of the whole audio pipeline (§8)."""

    pipeline_version: str
    dialogue: DialoguePreparationReceipt
    voice_cast: VoiceCastReceipt
    tts: TtsSynthesisReceipt
    alignment: AlignmentReceipt
    mix: Optional[AudioMixPlan] = None
    issues: List[AudioIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "dialogue": self.dialogue.to_dict(),
            "voice_cast": self.voice_cast.to_dict(),
            "tts": self.tts.to_dict(),
            "alignment": self.alignment.to_dict(),
            "mix": self.mix.to_dict() if self.mix else None,
            "issues": [i.to_dict() for i in self.issues],
        }


__all__ = [
    "AudioIssue",
    "DialoguePreparationReceipt",
    "VoiceCastReceipt",
    "TtsSynthesisReceipt",
    "AlignmentReceipt",
    "AudioPipelineReceipt",
]
