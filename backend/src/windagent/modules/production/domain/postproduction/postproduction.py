"""Post-production domain (Phase 16).

Deterministic EDL, transition, subtitle, encoding profile, frame validation
and verified deliverable — ported from ``core/domain/video_production/postproduction.py``
and ``intelligence/video/postproduction`` but provider-neutral and lean.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ProductionValidationError


class PostProductionStatus(StrEnum):
    DRAFT = "DRAFT"
    ASSEMBLING = "ASSEMBLING"
    VERIFIED = "VERIFIED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class TransitionType(StrEnum):
    CUT = "CUT"
    FADE = "FADE"
    DISSOLVE = "DISSOLVE"
    WIPE = "WIPE"
    MATCH_CUT = "MATCH_CUT"


class ContainerFormat(StrEnum):
    MP4 = "MP4"
    MOV = "MOV"
    MKV = "MKV"


class EncodingPreset(StrEnum):
    MAIN_1080P_H264 = "MAIN_1080P_H264"
    PROXY_720P_H264 = "PROXY_720P_H264"
    MAIN_4K_H264 = "MAIN_4K_H264"


@dataclass(frozen=True)
class TransitionPlan:
    transition_id: str
    transition_type: TransitionType
    duration_seconds: float = 0.5
    easing: str = "linear"

    def filter_expression(self) -> str:
        if self.transition_type == TransitionType.CUT or self.duration_seconds <= 0.0:
            return ""
        return f"xfade=transition=fade:duration={self.duration_seconds:.3f}"


@dataclass(frozen=True)
class SubtitleCue:
    cue_id: str
    start_time: float
    end_time: float
    text: str
    speaker: str = ""

    def validate_bounds(self, max_duration: float) -> bool:
        return 0.0 <= self.start_time < self.end_time <= max_duration + 0.1


@dataclass(frozen=True)
class SubtitleTrack:
    track_id: str
    cues: tuple[SubtitleCue, ...] = field(default_factory=tuple)

    @property
    def content_hash(self) -> str:
        data = [{"id": str(c.cue_id), "start": c.start_time, "end": c.end_time, "text": c.text, "speaker": c.speaker} for c in self.cues]
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class EncodingProfile:
    profile_id: str
    preset: EncodingPreset
    container: ContainerFormat
    video_codec: str
    video_crf: int
    resolution_width: int
    resolution_height: int
    frame_rate: int
    pixel_format: str
    audio_codec: str
    audio_sample_rate: int
    audio_channels: int
    audio_bitrate_kbps: int
    audio_loudness_target_lufs: float = -16.0
    audio_peak_ceiling_db: float = -1.0

    @property
    def content_hash(self) -> str:
        payload = {
            "profile_id": str(self.profile_id),
            "preset": str(self.preset),
            "container": str(self.container),
            "video_codec": self.video_codec,
            "video_crf": self.video_crf,
            "width": self.resolution_width,
            "height": self.resolution_height,
            "frame_rate": self.frame_rate,
            "pixel_format": self.pixel_format,
            "audio_codec": self.audio_codec,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
            "audio_bitrate_kbps": self.audio_bitrate_kbps,
            "loudness_target_lufs": self.audio_loudness_target_lufs,
            "peak_ceiling_db": self.audio_peak_ceiling_db,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def main_1080p_h264(cls) -> EncodingProfile:
        return cls(
            profile_id="enc_main_1080p",
            preset=EncodingPreset.MAIN_1080P_H264,
            container=ContainerFormat.MP4,
            video_codec="libx264",
            video_crf=18,
            resolution_width=1920,
            resolution_height=1080,
            frame_rate=30,
            pixel_format="yuv420p",
            audio_codec="aac",
            audio_sample_rate=48000,
            audio_channels=2,
            audio_bitrate_kbps=192,
        )

    @classmethod
    def proxy_720p_h264(cls) -> EncodingProfile:
        return cls(
            profile_id="enc_proxy_720p",
            preset=EncodingPreset.PROXY_720P_H264,
            container=ContainerFormat.MP4,
            video_codec="libx264",
            video_crf=24,
            resolution_width=1280,
            resolution_height=720,
            frame_rate=30,
            pixel_format="yuv420p",
            audio_codec="aac",
            audio_sample_rate=44100,
            audio_channels=2,
            audio_bitrate_kbps=96,
        )


@dataclass(frozen=True)
class EditDecisionItem:
    shot_id: str
    clip_hash: str
    in_point: float = 0.0
    out_point: float = 5.0
    target_duration: float = 5.0
    transition_in: TransitionPlan | None = None
    frame_start: int = 0
    frame_end: int = 0
    audio_offset_seconds: float = 0.0


@dataclass(frozen=True)
class EditDecisionList:
    edl_id: str
    project_id: str
    revision_id: str
    items: tuple[EditDecisionItem, ...]
    audio_mix_plan_id: str
    subtitle_track_id: str | None = None
    encoding_profile: EncodingProfile = field(default_factory=EncodingProfile.main_1080p_h264)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: PostProductionStatus = PostProductionStatus.DRAFT
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_duration_seconds(self) -> float:
        total = sum(item.target_duration for item in self.items)
        for item in self.items:
            if item.transition_in and item.transition_in.duration_seconds > 0:
                total -= item.transition_in.duration_seconds
        return max(0.0, total)

    @property
    def edl_hash(self) -> str:
        payload_data = {
            "edl_id": str(self.edl_id),
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "items": [
                {
                    "shot_id": str(item.shot_id),
                    "clip_hash": item.clip_hash,
                    "in_point": item.in_point,
                    "out_point": item.out_point,
                    "target_duration": item.target_duration,
                    "frame_start": item.frame_start,
                    "frame_end": item.frame_end,
                    "audio_offset_seconds": item.audio_offset_seconds,
                    "transition_in": item.transition_in.filter_expression() if item.transition_in else "",
                }
                for item in self.items
            ],
            "audio_mix_plan_id": str(self.audio_mix_plan_id),
            "subtitle_track_id": str(self.subtitle_track_id) if self.subtitle_track_id else None,
            "encoding_profile": str(self.encoding_profile.profile_id),
        }
        encoded = json.dumps(payload_data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def validate(self) -> None:
        if not self.items:
            raise ProductionValidationError("EDL requires at least one item.")
        for item in self.items:
            if not item.clip_hash:
                raise ProductionValidationError("EDL item clip_hash cannot be blank.", context={"shot_id": item.shot_id})


# Pydantic wrappers for service layer convenience
class EdlViewModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    edl_id: str
    project_id: str
    revision_id: str
    title: str = ""
    status: PostProductionStatus = PostProductionStatus.DRAFT
    edl_hash: str = ""
    total_duration: float = 0.0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ContainerFormat",
    "EditDecisionItem",
    "EditDecisionList",
    "EdlViewModel",
    "EncodingPreset",
    "EncodingProfile",
    "PostProductionStatus",
    "SubtitleCue",
    "SubtitleTrack",
    "TransitionPlan",
    "TransitionType",
]
