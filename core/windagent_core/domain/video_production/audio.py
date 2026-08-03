"""
Audio production domain (plan 06 Phase 21, §7-§8).

Phase 21 adds the audio pipeline domain models used to build a precise,
voice-consistent dialogue/narration track with word timestamps and a versioned
mix plan. It does NOT depend on any provider TTS — providers are adapters.

Models:

```text
CharacterVoiceProfile  — voice bound to a CHARACTER ID (never a display name),
                         with provider/model/voice/version + rights/consent.
WordTimestamp          — per-word start/end + confidence from forced alignment.
DialogueTrack          — one prepared dialogue line + its TTS asset + timing.
SoundEffectCue         — licensed SFX/ambience cue on the timeline/shot.
MusicCue               — licensed BGM cue on the timeline/shot.
AudioMixPlan           — versioned mix policy (ducking/loudness/peak) + cues.
```

Rules (plan §7-§8):

- a voice profile binds to `character_id`, never a display name; real-voice
  likenesses require rights/consent metadata + approval;
- a TTS audio asset records content hash, sample rate, channel layout and
  duration — an invalid output is never published;
- every audio asset carries provenance (provider/model/voice/version,
  license/terms) and is traceable;
- text revision creates a NEW audio revision and invalidates exactly the
  downstream audio/mix artifacts (BGM change -> mix/final only, never clips).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from windagent_core.domain.video_production.enums import (
    AudioAlignmentStatus,
    AudioCueKind,
    AudioIntentType,
    AudioInvalidationScope,
    LicenseState,
    VoiceRightsState,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
    CharacterId,
    CharacterVoiceProfileId,
    DialogueLineId,
    DialogueTrackId,
    MusicCueId,
    ProductionRevisionId,
    ShotId,
    SoundEffectCueId,
    TtsAudioAssetId,
    VideoProjectId,
    WordTimestampId,
)

AUDIO_PIPELINE_VERSION = "1.0.0"
AUDIO_MIX_POLICY_VERSION = "1.0.0"


class CharacterVoiceProfile(BaseModel):
    """Voice cast for one character (plan §7, §8.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: CharacterVoiceProfileId
    character_id: CharacterId
    voice_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    voice_version: str = Field(min_length=1)
    language: str = "vi-VN"
    locale: str = "vi-VN"
    rights_state: VoiceRightsState = VoiceRightsState.UNKNOWN
    rights_metadata: Dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    approval_actor: str = ""
    preview_only: bool = True  # a preview never becomes final without approval

    def profile_hash(self) -> str:
        """Deterministic hash over the voice identity + version (plan §8.3)."""
        canonical = json.dumps(
            {
                "character_id": str(self.character_id),
                "provider": self.provider,
                "model": self.model,
                "voice_id": self.voice_id,
                "voice_version": self.voice_version,
                "language": self.language,
                "locale": self.locale,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": str(self.profile_id),
            "character_id": str(self.character_id),
            "voice_name": self.voice_name,
            "provider": self.provider,
            "model": self.model,
            "voice_id": self.voice_id,
            "voice_version": self.voice_version,
            "language": self.language,
            "locale": self.locale,
            "rights_state": self.rights_state.value,
            "rights_metadata": self.rights_metadata,
            "approved": self.approved,
            "approval_actor": self.approval_actor,
            "preview_only": self.preview_only,
        }


class TtsAudioAsset(BaseModel):
    """Validated TTS output audio (plan §8.3 — invalid output never publishes)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    asset_id: TtsAudioAssetId
    content_hash: str = Field(min_length=64, max_length=64)
    sample_rate: int = Field(gt=0)
    channel_layout: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    byte_size: int = Field(ge=0)
    source_request_hash: str = Field(min_length=64, max_length=64)
    provider: str = ""
    model: str = ""
    voice_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": str(self.asset_id),
            "content_hash": self.content_hash,
            "sample_rate": self.sample_rate,
            "channel_layout": self.channel_layout,
            "duration_seconds": self.duration_seconds,
            "byte_size": self.byte_size,
            "source_request_hash": self.source_request_hash,
            "provider": self.provider,
            "model": self.model,
            "voice_id": self.voice_id,
        }


class WordTimestamp(BaseModel):
    """Forced-alignment word timing (plan §8.4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    timestamp_id: WordTimestampId
    word: str = Field(min_length=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _end_after_start(self) -> "WordTimestamp":
        if self.end_seconds < self.start_seconds:
            raise ValueError(
                f"WordTimestamp end {self.end_seconds} < start {self.start_seconds}"
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_id": str(self.timestamp_id),
            "word": self.word,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "confidence": self.confidence,
        }


class DialogueTrack(BaseModel):
    """One prepared dialogue line + its TTS asset + alignment (plan §8.1-§8.4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: DialogueTrackId
    dialogue_id: DialogueLineId
    character_id: CharacterId
    text: str = Field(min_length=1)
    intent_type: AudioIntentType = AudioIntentType.SPOKEN_DIALOGUE
    language: str = "vi-VN"
    locale: str = "vi-VN"
    target_duration_seconds: float = Field(gt=0)
    # Voice profile hash is bound only when TTS runs (§8.3); a prepared track
    # carries "" until then (casting is a separate stage, §8.2).
    voice_profile_hash: str = ""
    audio_revision: int = Field(default=1)
    audio: Optional[TtsAudioAsset] = None
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)
    alignment_status: AudioAlignmentStatus = AudioAlignmentStatus.ALIGNED
    alignment_confidence: float = Field(default=1.0, ge=0, le=1)
    speaking_intent: str = ""
    prepared_text: str = ""
    pronunciation_lexicon_version: str = ""
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @property
    def has_valid_audio(self) -> bool:
        """Audio is usable when present and not blocked by a failed alignment.

        `TIMING_PROPOSED` counts as valid: the track still fits after the
        timing adjustment proposal, it is never silently cut (plan §8.4).
        """
        return self.audio is not None and self.alignment_status in (
            AudioAlignmentStatus.ALIGNED,
            AudioAlignmentStatus.TIMING_PROPOSED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": str(self.track_id),
            "dialogue_id": str(self.dialogue_id),
            "character_id": str(self.character_id),
            "text": self.text,
            "intent_type": self.intent_type.value,
            "language": self.language,
            "locale": self.locale,
            "target_duration_seconds": self.target_duration_seconds,
            "voice_profile_hash": self.voice_profile_hash,
            "audio_revision": self.audio_revision,
            "audio": self.audio.to_dict() if self.audio else None,
            "word_timestamps": [w.to_dict() for w in self.word_timestamps],
            "alignment_status": self.alignment_status.value,
            "alignment_confidence": self.alignment_confidence,
            "speaking_intent": self.speaking_intent,
            "prepared_text": self.prepared_text,
            "pronunciation_lexicon_version": self.pronunciation_lexicon_version,
            "provenance": self.provenance,
        }


class SoundEffectCue(BaseModel):
    """Licensed SFX/ambience cue bound to a timeline position/shot (plan §8.5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    cue_id: SoundEffectCueId
    kind: AudioCueKind = AudioCueKind.SFX
    shot_id: Optional[ShotId] = None
    timeline_start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    fade_in_seconds: float = Field(default=0, ge=0)
    fade_out_seconds: float = Field(default=0, ge=0)
    license_state: LicenseState = LicenseState.UNKNOWN
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": str(self.cue_id),
            "kind": self.kind.value,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "timeline_start_seconds": self.timeline_start_seconds,
            "duration_seconds": self.duration_seconds,
            "fade_in_seconds": self.fade_in_seconds,
            "fade_out_seconds": self.fade_out_seconds,
            "license_state": self.license_state.value,
            "provenance": self.provenance,
        }


class MusicCue(BaseModel):
    """Licensed BGM cue bound to the timeline (plan §8.5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    cue_id: MusicCueId
    kind: AudioCueKind = AudioCueKind.BGM
    timeline_start_seconds: float = Field(ge=0)
    timeline_end_seconds: float = Field(gt=0)
    fade_in_seconds: float = Field(default=0, ge=0)
    fade_out_seconds: float = Field(default=0, ge=0)
    license_state: LicenseState = LicenseState.UNKNOWN
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": str(self.cue_id),
            "kind": self.kind.value,
            "timeline_start_seconds": self.timeline_start_seconds,
            "timeline_end_seconds": self.timeline_end_seconds,
            "fade_in_seconds": self.fade_in_seconds,
            "fade_out_seconds": self.fade_out_seconds,
            "license_state": self.license_state.value,
            "provenance": self.provenance,
        }


class AudioMixPlan(BaseModel):
    """Versioned mix plan: dialogue tracks + cues + technical policy (§8.5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    mix_id: AudioMixPlanId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    dialogue_tracks: List[DialogueTrack] = Field(default_factory=list)
    sound_effect_cues: List[SoundEffectCue] = Field(default_factory=list)
    music_cues: List[MusicCue] = Field(default_factory=list)
    dialogue_ducking_db: float = Field(default=-12.0)
    loudness_target_lufs: float = Field(default=-16.0)
    peak_ceiling_db: float = Field(default=-1.0)
    mix_policy_version: str = AUDIO_MIX_POLICY_VERSION
    command_manifest: Dict[str, Any] = Field(default_factory=dict)
    mix_hash: str = ""

    def invalidated_scope(self, changed_kind: "AudioCueKind | str") -> AudioInvalidationScope:
        """Downstream invalidation of an audio change (plan §8.5).

        Only BGM is clip-safe: a music change invalidates the mix/final cut
        but NEVER the visual clips. SFX/ambience changes invalidate the mix
        (they live on the audio timeline, not the visual assets); a dialogue
        change invalidates its own track AND the mix + final cut. Accepts
        an `AudioCueKind` member or the string "dialogue" (typed call sites
        pass the enum; dialogue is not a cue kind).
        """
        kind = changed_kind.value if isinstance(changed_kind, AudioCueKind) else changed_kind
        if kind in (AudioCueKind.BGM.value, AudioCueKind.SFX.value, AudioCueKind.AMBIENCE.value):
            return AudioInvalidationScope.MIX_ONLY
        if kind == "dialogue":
            return AudioInvalidationScope.TRACK_AND_MIX
        return AudioInvalidationScope.NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mix_id": str(self.mix_id),
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "dialogue_tracks": [t.to_dict() for t in self.dialogue_tracks],
            "sound_effect_cues": [c.to_dict() for c in self.sound_effect_cues],
            "music_cues": [c.to_dict() for c in self.music_cues],
            "dialogue_ducking_db": self.dialogue_ducking_db,
            "loudness_target_lufs": self.loudness_target_lufs,
            "peak_ceiling_db": self.peak_ceiling_db,
            "mix_policy_version": self.mix_policy_version,
            "command_manifest": self.command_manifest,
            "mix_hash": self.mix_hash,
        }


def compute_mix_hash(*, project_id: object, revision_id: object, mix_payload: Dict[str, Any], mix_policy_version: str) -> str:
    """Deterministic SHA-256 over the canonical mix payload + policy version."""
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "mix_policy_version": mix_policy_version,
            "mix": mix_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "AUDIO_PIPELINE_VERSION",
    "AUDIO_MIX_POLICY_VERSION",
    "CharacterVoiceProfile",
    "TtsAudioAsset",
    "WordTimestamp",
    "DialogueTrack",
    "SoundEffectCue",
    "MusicCue",
    "AudioMixPlan",
    "compute_mix_hash",
]
