"""
Legacy compatibility — `GenerationMode` / `GenerationModeReasonCode`.

Retired from `windagent_core.domain.video_production.enums` during VP3D
Stage A. Kept ONLY for the bounded legacy reader / migration window (see
`legacy_v1.SUNSET.md`). The engine-neutral runtime never references these.
"""

from __future__ import annotations

from enum import Enum


class GenerationMode(str, Enum):
    """Legacy generative-video generation modes (retired in Stage A)."""

    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    FRAMES_TO_VIDEO = "FRAMES_TO_VIDEO"
    INGREDIENTS_TO_VIDEO = "INGREDIENTS_TO_VIDEO"
    VIDEO_EXTENSION = "VIDEO_EXTENSION"
    VIDEO_TO_VIDEO = "VIDEO_TO_VIDEO"
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"


class GenerationModeReasonCode(str, Enum):
    """Legacy machine-readable reason behind a generation mode decision."""

    NO_MANDATORY_REFERENCE = "NO_MANDATORY_REFERENCE"
    IDENTITY_REFERENCE_REQUIRED = "IDENTITY_REFERENCE_REQUIRED"
    LOCATION_REFERENCE_REQUIRED = "LOCATION_REFERENCE_REQUIRED"
    FRAMES_REQUIRED = "FRAMES_REQUIRED"
    MOTION_CONTINUATION = "MOTION_CONTINUATION"
    CLIP_TRANSFORMATION = "CLIP_TRANSFORMATION"


__all__ = ["GenerationMode", "GenerationModeReasonCode"]
