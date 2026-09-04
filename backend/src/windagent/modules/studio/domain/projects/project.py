"""Top-level Studio project aggregate (container for series)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class Project(BaseModel):
    """Mutable-capable top-level Project owning series."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(default="")
    owner_id: str = Field(default="system")
    series_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    optimistic_version: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Project title cannot be blank.")
        return v.strip()

    def with_series(self, series_id: str) -> Project:
        if series_id in self.series_ids:
            return self
        return self.model_copy(
            update={
                "series_ids": (*self.series_ids, series_id),
                "updated_at": utc_now(),
                "optimistic_version": self.optimistic_version + 1,
            }
        )

    def rename(self, title: str, *, expected_version: int | None = None) -> Project:
        if expected_version is not None and expected_version != self.optimistic_version:
            from ..errors import StudioStaleRevisionError

            raise StudioStaleRevisionError(
                "Project version mismatch.",
                context={
                    "project_id": self.project_id,
                    "expected_version": expected_version,
                    "current_version": self.optimistic_version,
                },
            )
        normalized = title.strip()
        if not normalized:
            raise StudioValidationError("Project title cannot be blank.")
        if normalized == self.title:
            return self
        return self.model_copy(
            update={"title": normalized, "updated_at": utc_now(), "optimistic_version": self.optimistic_version + 1}
        )


__all__ = ["Project", "utc_now"]
