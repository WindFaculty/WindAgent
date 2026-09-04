"""Canonical Studio ``SeriesProject`` aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioStaleRevisionError, StudioValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class SeriesProject(BaseModel):
    """Top-level canonical Studio aggregate owning creative episodes."""

    model_config = ConfigDict(frozen=True, extra="allow")

    series_id: str = Field(min_length=1)
    project_id: str | None = Field(default=None)
    title: str = Field(min_length=1)
    description: str = Field(default="")
    episode_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    optimistic_version: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("SeriesProject title cannot be blank.")
        return v.strip()

    def with_episode(self, episode_id: str) -> SeriesProject:
        if episode_id in self.episode_ids:
            return self
        return self.model_copy(
            update={
                "episode_ids": (*self.episode_ids, episode_id),
                "updated_at": utc_now(),
                "optimistic_version": self.optimistic_version + 1,
            }
        )

    def edit(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> SeriesProject:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise StudioStaleRevisionError(
                "Series version mismatch.",
                context={
                    "series_id": self.series_id,
                    "expected_version": expected_version,
                    "current_version": self.optimistic_version,
                },
            )
        changes: dict[str, Any] = {}
        if title is not None and title.strip() != self.title:
            changes["title"] = title.strip()
        if description is not None and description != self.description:
            changes["description"] = description
        if metadata_patch:
            merged = dict(self.metadata)
            merged.update(metadata_patch)
            if merged != self.metadata:
                changes["metadata"] = merged
        if not changes:
            return self
        return self.model_copy(
            update={**changes, "updated_at": utc_now(), "optimistic_version": self.optimistic_version + 1}
        )


__all__ = ["SeriesProject", "utc_now"]
