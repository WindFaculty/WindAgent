"""
Post-Production Domain Entities & Value Objects (Phase 22 — plan 06 §11-§15).

Defines deterministic models for Edit Decision Lists (EDL), Transition Plans,
Subtitle Tracks, Encoding Profiles, Subprocess Receipts, Quality Verification,
and Final Deliverables.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from windagent_core.domain.video_production.enums import (
    ContainerFormat,
    EncodingPreset,
    PostProductionIssueCode,
    PostProductionStatus,
    PostProductionVerificationStatus,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
    EditDecisionListId,
    EncodingProfileId,
    FinalDeliverableId,
    PostProductionJobId,
    ProductionRevisionId,
    ShotId,
    SubtitleCueId,
    SubtitleTrackId,
    TransitionPlanId,
    VideoProjectId,
)


@dataclass(frozen=True)
class TransitionPlan:
    """Transition between two sequential video shots."""

    transition_id: TransitionPlanId
    transition_type: TransitionType
    duration_seconds: float = 0.5
    easing: str = "linear"

    def filter_expression(self) -> str:
        """Derive deterministic FFmpeg xfade transition filter expression."""
        if self.transition_type == TransitionType.CUT or self.duration_seconds <= 0.0:
            return ""
        # Default xfade transition
        return f"xfade=transition=fade:duration={self.duration_seconds:.3f}"


@dataclass(frozen=True)
class SubtitleCue:
    """Individual subtitle text cue timed to video timeline."""

    cue_id: SubtitleCueId
    start_time: float
    end_time: float
    text: str
    speaker: str = ""

    def validate_bounds(self, max_duration: float) -> bool:
        return 0.0 <= self.start_time < self.end_time <= max_duration + 0.1


@dataclass(frozen=True)
class SubtitleTrack:
    """Timed subtitle track aggregate."""

    track_id: SubtitleTrackId
    cues: tuple[SubtitleCue, ...] = field(default_factory=tuple)

    @property
    def content_hash(self) -> str:
        data = [
            {
                "id": str(c.cue_id),
                "start": c.start_time,
                "end": c.end_time,
                "text": c.text,
                "speaker": c.speaker,
            }
            for c in self.cues
        ]
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class EncodingProfile:
    """Standardized video/audio encoding parameters."""

    profile_id: EncodingProfileId
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

    @classmethod
    def main_1080p_h264(cls) -> EncodingProfile:
        return cls(
            profile_id=EncodingProfileId("enc_main_1080p"),
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
            audio_loudness_target_lufs=-16.0,
            audio_peak_ceiling_db=-1.0,
        )

    @classmethod
    def proxy_720p_h264(cls) -> EncodingProfile:
        return cls(
            profile_id=EncodingProfileId("enc_proxy_720p"),
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
            audio_loudness_target_lufs=-16.0,
            audio_peak_ceiling_db=-1.0,
        )


@dataclass(frozen=True)
class EditDecisionItem:
    """Item in an Edit Decision List referencing a content-addressed clip."""

    shot_id: ShotId
    clip_hash: str
    in_point: float = 0.0
    out_point: float = 5.0
    target_duration: float = 5.0
    transition_in: TransitionPlan | None = None


@dataclass(frozen=True)
class EditDecisionList:
    """Deterministic Edit Decision List aggregate."""

    edl_id: EditDecisionListId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    items: tuple[EditDecisionItem, ...]
    audio_mix_plan_id: AudioMixPlanId
    subtitle_track_id: SubtitleTrackId | None = None
    encoding_profile: EncodingProfile = field(
        default_factory=EncodingProfile.main_1080p_h264
    )

    @property
    def total_duration_seconds(self) -> float:
        total = sum(item.target_duration for item in self.items)
        # Subtract transition overlap durations
        for item in self.items:
            if item.transition_in and item.transition_in.duration_seconds > 0:
                total -= item.transition_in.duration_seconds
        return max(0.0, total)

    @property
    def edl_hash(self) -> str:
        """Deterministic content SHA-256 hash of the EDL."""
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
                    "transition_in": item.transition_in.filter_expression()
                    if item.transition_in
                    else "",
                }
                for item in self.items
            ],
            "audio_mix_plan_id": str(self.audio_mix_plan_id),
            "subtitle_track_id": str(self.subtitle_track_id)
            if self.subtitle_track_id
            else None,
            "encoding_profile": str(self.encoding_profile.profile_id),
        }
        encoded = json.dumps(payload_data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class FfmpegCommandReceipt:
    """Execution receipt for an FFmpeg / ffprobe command invocation."""

    command_id: str
    argv: tuple[str, ...]
    return_code: int
    execution_time_seconds: float
    stdout_snippet: str
    stderr_snippet: str
    input_hashes: tuple[str, ...]
    output_hash: str


@dataclass(frozen=True)
class FfprobeVerificationReceipt:
    """Post-render quality verification receipt."""

    receipt_id: str
    is_valid: bool
    format_name: str
    duration_seconds: float
    video_stream_found: bool
    audio_stream_found: bool
    width: int
    height: int
    frame_rate: float
    pixel_format: str
    loudness_lufs: float
    peak_db: float
    sample_frames_decoded: int
    issues: tuple[PostProductionIssueCode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VerifiedDeliverable:
    """Verified final media deliverable output.

    Distinct from the canonical published-deliverable record
    (`asset.FinalDeliverable`): this is the post-production verification
    output (edl/render/thumbnail hashes + verification status), not the
    publishable asset record.
    """

    deliverable_id: FinalDeliverableId
    edl_id: EditDecisionListId
    edl_hash: str
    final_video_hash: str
    proxy_video_hash: str
    thumbnail_hash: str
    duration_seconds: float
    verification_status: PostProductionVerificationStatus
    verified_at: str


@dataclass(frozen=True)
class PostProductionJob:
    """Post-production assembly & verification job lifecycle state."""

    job_id: PostProductionJobId
    edl_id: EditDecisionListId
    status: PostProductionStatus
    error_message: str = ""
    command_receipt_hashes: tuple[str, ...] = field(default_factory=tuple)
    deliverable_id: FinalDeliverableId | None = None
