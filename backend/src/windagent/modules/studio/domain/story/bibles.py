"""Story bible content models."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .canonical import StoryContent


class StoryBible(StoryContent):
    artifact_type: str = Field(default="StoryBible")
    series_id: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    themes: tuple[str, ...] = Field(default_factory=tuple)
    tone: str = Field(default="")
    world_summary: str = Field(default="")
    character_summaries: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    narrative_arc: str = Field(default="")

    SUMMARY_FIELDS = ("series_id", "premise", "themes")


class WorldBible(StoryContent):
    artifact_type: str = Field(default="WorldBible")
    series_id: str = Field(min_length=1)
    setting: str = Field(min_length=1)
    locations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    props: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    rules: tuple[str, ...] = Field(default_factory=tuple)

    SUMMARY_FIELDS = ("series_id", "setting")


class CharacterCanon(StoryContent):
    artifact_type: str = Field(default="CharacterCanon")
    series_id: str = Field(min_length=1)
    characters: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    SUMMARY_FIELDS = ("series_id",)


__all__ = ["CharacterCanon", "StoryBible", "WorldBible"]
