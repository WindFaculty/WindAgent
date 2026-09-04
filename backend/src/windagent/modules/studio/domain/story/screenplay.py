"""Screenplay content models."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .canonical import StoryContent


class ScreenplayDraft(StoryContent):
    artifact_type: str = Field(default="ScreenplayDraft")
    episode_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scenes: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    dialogue_lines: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    draft_number: int = Field(default=1, ge=1)

    SUMMARY_FIELDS = ("episode_id", "title", "draft_number")


class ReviewReport(StoryContent):
    artifact_type: str = Field(default="ReviewReport")
    episode_id: str = Field(min_length=1)
    checkpoint: str = Field(min_length=1)
    verdict: str = Field(default="APPROVED")
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    findings: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    SUMMARY_FIELDS = ("episode_id", "checkpoint", "verdict", "score")


class LockedScreenplayReceipt(StoryContent):
    artifact_type: str = Field(default="LockedScreenplayReceipt")
    episode_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)  # type: ignore[assignment]

    SUMMARY_FIELDS = ("episode_id", "revision_id")


class LockedScreenplayPackage(StoryContent):
    artifact_type: str = Field(default="LockedScreenplayPackage")
    episode_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    package_hash: str = Field(min_length=64, max_length=64)
    artifacts: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    SUMMARY_FIELDS = ("episode_id", "revision_id", "package_hash")


__all__ = [
    "LockedScreenplayPackage",
    "LockedScreenplayReceipt",
    "ReviewReport",
    "ScreenplayDraft",
]
