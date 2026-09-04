"""Ideation content models (IdeaCandidateSet / SelectedIdea)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .canonical import StoryContent


class IdeaCandidate(StoryContent):
    artifact_type: str = Field(default="IdeaCandidateSet")
    idea_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    logline: str = Field(default="")
    synopsis: str = Field(default="")
    tone: str = Field(default="")
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    SUMMARY_FIELDS = ("idea_id", "title", "logline", "score")


class IdeaCandidateSet(StoryContent):
    artifact_type: str = Field(default="IdeaCandidateSet")
    candidates: tuple[IdeaCandidate, ...] = Field(default_factory=tuple)
    brief_ref: str = Field(default="")
    selection_policy: str = Field(default="highest_score")

    SUMMARY_FIELDS = ("artifact_type", "schema_version")

    def selected(self, candidate_id: str) -> IdeaCandidate | None:
        for candidate in self.candidates:
            if candidate.idea_id == candidate_id:
                return candidate
        return None


class SelectedIdea(StoryContent):
    artifact_type: str = Field(default="SelectedIdea")
    candidate_id: str = Field(min_length=1)
    idea_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    logline: str = Field(default="")
    rationale: str = Field(default="")

    SUMMARY_FIELDS = ("candidate_id", "idea_id", "title")


__all__ = ["IdeaCandidate", "IdeaCandidateSet", "SelectedIdea"]
