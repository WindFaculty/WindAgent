"""Outline content models (BeatSheet / EpisodeOutline)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .canonical import StoryContent


class BeatSheet(StoryContent):
    artifact_type: str = Field(default="BeatSheet")
    episode_id: str = Field(min_length=1)
    beats: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    total_duration_minutes: float = Field(default=0.0, ge=0.0)

    SUMMARY_FIELDS = ("episode_id", "total_duration_minutes")


class EpisodeOutline(StoryContent):
    artifact_type: str = Field(default="EpisodeOutline")
    episode_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scenes: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    estimated_duration_minutes: float = Field(default=0.0, ge=0.0)

    SUMMARY_FIELDS = ("episode_id", "title", "estimated_duration_minutes")


__all__ = ["BeatSheet", "EpisodeOutline"]
