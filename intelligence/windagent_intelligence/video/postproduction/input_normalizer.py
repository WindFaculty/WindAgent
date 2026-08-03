"""
Input Normalizer Service (Phase 22 — plan 06 §13.2).

Validates input streams before concatenation, normalizes time base, frame rate,
resolution, pixel format, and audio sample rate according to target profile.
Applies aspect-ratio padding (16:9) without silent stretching.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from windagent_core.domain.video_production.postproduction import (
    EncodingProfile,
)
from windagent_intelligence.video.postproduction.models import (
    InputMediaMetadata,
    NormalizationSpec,
)


class InputNormalizer:
    """Computes normalization specs and FFmpeg filter chains for input clips."""

    def __init__(self, target_profile: EncodingProfile) -> None:
        self.profile = target_profile

    def inspect_metadata(
        self,
        file_path: Path,
        duration: float = 5.0,
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        has_audio: bool = True,
    ) -> InputMediaMetadata:
        """Create structured metadata record for an input media file."""
        content_bytes = (
            file_path.read_bytes()
            if file_path.exists()
            else f"mock_clip_{file_path.name}".encode("utf-8")
        )
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        return InputMediaMetadata(
            file_path=file_path,
            content_hash=content_hash,
            duration_seconds=duration,
            width=width,
            height=height,
            frame_rate=fps,
            video_codec="h264",
            pixel_format="yuv420p",
            has_audio=has_audio,
            audio_codec="aac" if has_audio else "",
            audio_sample_rate=48000 if has_audio else 0,
            audio_channels=2 if has_audio else 0,
            rotation_degrees=0,
        )

    def compute_normalization_spec(
        self, metadata: InputMediaMetadata
    ) -> NormalizationSpec:
        """Compute required normalization steps and FFmpeg video/audio filter expressions."""
        needs_scaling = (
            metadata.width != self.profile.resolution_width
            or metadata.height != self.profile.resolution_height
        )
        # Check aspect ratio
        target_aspect = (
            self.profile.resolution_width / self.profile.resolution_height
        )
        input_aspect = (
            metadata.width / metadata.height if metadata.height > 0 else target_aspect
        )

        needs_padding = abs(input_aspect - target_aspect) > 0.01
        needs_fps_conversion = abs(metadata.frame_rate - self.profile.frame_rate) > 0.01
        needs_audio_resampling = (
            metadata.has_audio
            and metadata.audio_sample_rate != self.profile.audio_sample_rate
        )

        # Build video filter string
        v_filters: list[str] = []
        if needs_scaling or needs_padding:
            tw = self.profile.resolution_width
            th = self.profile.resolution_height
            v_filters.append(
                f"scale=w={tw}:h={th}:force_original_aspect_ratio=decrease,"
                f"pad=w={tw}:h={th}:x=(ow-iw)/2:y=(oh-ih)/2:color=black"
            )
        if needs_fps_conversion:
            v_filters.append(f"fps={self.profile.frame_rate}")

        v_filters.append(f"format={self.profile.pixel_format}")
        filter_graph = ",".join(v_filters)

        return NormalizationSpec(
            file_path=metadata.file_path,
            target_profile=self.profile,
            needs_scaling=needs_scaling,
            needs_padding=needs_padding,
            needs_fps_conversion=needs_fps_conversion,
            needs_audio_resampling=needs_audio_resampling,
            filter_graph=filter_graph,
        )
