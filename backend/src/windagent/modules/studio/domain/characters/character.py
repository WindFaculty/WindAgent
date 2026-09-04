"""Canonical character aggregate (Plan B identity, Plan A lifecycle)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class Character(BaseModel):
    """Immutable canon character; episodes reference by ``character_id``."""

    model_config = ConfigDict(frozen=True, extra="allow")

    character_id: str = Field(min_length=1)
    series_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    display_name: str = Field(default="")
    role: str = Field(default="supporting")
    archetype: str = Field(default="")
    description: str = Field(default="")
    traits: tuple[str, ...] = Field(default_factory=tuple)
    backstory: str = Field(default="")
    portrait_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Character name cannot be blank.")
        return v.strip()

    def edit(
        self,
        *,
        display_name: str | None = None,
        description: str | None = None,
        traits: tuple[str, ...] | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> Character:
        changes: dict[str, Any] = {}
        if display_name is not None and display_name != self.display_name:
            changes["display_name"] = display_name
        if description is not None and description != self.description:
            changes["description"] = description
        if traits is not None and tuple(traits) != self.traits:
            changes["traits"] = tuple(traits)
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


__all__ = ["Character", "utc_now"]
