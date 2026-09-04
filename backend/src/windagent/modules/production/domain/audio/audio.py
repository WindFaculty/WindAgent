"""Audio production domain (Phase 16).

Provider-neutral audio models: voice profiles bound to character IDs,
dialogue tracks with TTS assets + timing, mix plan with loudness policy.

Rules:
- voice profile binds to ``character_id``, never display name;
- TTS output records content hash, sample rate, channels, duration;
- every asset carries provenance (provider/model/voice/version, license);
- text revision creates a NEW audio revision and invalidates downstream.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ProductionValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class AudioTrackKind(StrEnum):
    DIALOGUE = "DIALOGUE"
    SFX = "SFX"
    MUSIC = "MUSIC"
    AMBIENCE = "AMBIENCE"


class VoiceRightsState(StrEnum):
    CLEARED = "CLEARED"
    PENDING = "PENDING"
    DENIED = "DENIED"


class AudioTrack(BaseModel):
    """One prepared dialogue/SFX/Music cue."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    kind: AudioTrackKind = AudioTrackKind.DIALOGUE
    title: str = Field(min_length=1)
    character_id: str | None = None
    dialogue_text: str = ""
    source_path: str = ""
    source_hash: str = Field(default="", min_length=0, max_length=64)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    channels: int = Field(default=1, ge=1, le=8)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    language: str = Field(default="en")
    voice_profile_id: str | None = None
    rights_state: VoiceRightsState = VoiceRightsState.PENDING
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MixTrack(BaseModel):
    """One track reference inside a mix plan."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_kind: AudioTrackKind = AudioTrackKind.DIALOGUE
    track_id: str = Field(min_length=1)
    source_hash: str = Field(default="")
    sample_rate: int = Field(default=48000, ge=8000)
    channels: int = Field(default=1, ge=1, le=8)
    gain_db: float = 0.0


class AudioMixPlan(BaseModel):
    """Versioned loudness/peak mix policy + its tracks."""

    model_config = ConfigDict(frozen=True, extra="allow")

    mix_plan_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(default="main")
    tracks: tuple[MixTrack, ...] = Field(default_factory=tuple)
    loudness_target_lufs: float = -16.0
    peak_ceiling_db: float = -1.0
    policy_version: str = "loudness-v1"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        payload = {
            "mix_plan_id": self.mix_plan_id,
            "project_id": self.project_id,
            "tracks": [
                {
                    "kind": str(t.track_kind),
                    "track_id": t.track_id,
                    "source_hash": t.source_hash,
                    "sample_rate": t.sample_rate,
                    "channels": t.channels,
                    "gain_db": t.gain_db,
                }
                for t in self.tracks
            ],
            "loudness_target_lufs": self.loudness_target_lufs,
            "peak_ceiling_db": self.peak_ceiling_db,
            "policy_version": self.policy_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def validate_mix(self) -> None:
        if not self.tracks:
            raise ProductionValidationError("Mix plan requires at least one track.")
        for track in self.tracks:
            if track.sample_rate < 8000:
                raise ProductionValidationError("Track sample_rate too low.")


class VoiceProfile(BaseModel):
    """Voice bound to a character ID (never display name)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    language: str = Field(default="en")
    rights_state: VoiceRightsState = VoiceRightsState.PENDING
    consent_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


__all__ = ["AudioMixPlan", "AudioTrack", "AudioTrackKind", "MixTrack", "VoiceProfile", "VoiceRightsState", "utc_now"]
