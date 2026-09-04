"""Storyboard aggregate (episode scene board)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class StoryboardPanel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    panel_id: str = Field(min_length=1)
    scene_index: int = Field(ge=0)
    description: str = Field(min_length=1)
    camera: str = Field(default="")
    dialogue_refs: tuple[str, ...] = Field(default_factory=tuple)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Storyboard(BaseModel):
    """Episode storyboard owning ordered panels."""

    model_config = ConfigDict(frozen=True, extra="allow")

    storyboard_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    series_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    panels: tuple[StoryboardPanel, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Storyboard title cannot be blank.")
        return v.strip()

    def with_panel(self, panel: StoryboardPanel) -> Storyboard:
        if any(existing.panel_id == panel.panel_id for existing in self.panels):
            return self
        return self.model_copy(
            update={
                "panels": (*self.panels, panel),
                "updated_at": utc_now(),
                "optimistic_version": self.optimistic_version + 1,
            }
        )

    def reorder(self, panel_ids: tuple[str, ...]) -> Storyboard:
        indexed = {panel.panel_id: panel for panel in self.panels}
        if set(panel_ids) != set(indexed):
            raise StudioValidationError("Reorder must include exactly the current panel ids.")
        ordered = tuple(indexed[panel_id] for panel_id in panel_ids)
        return self.model_copy(
            update={"panels": ordered, "updated_at": utc_now(), "optimistic_version": self.optimistic_version + 1}
        )


__all__ = ["Storyboard", "StoryboardPanel", "utc_now"]
