"""World bible aggregate (locations, props, rules)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorldLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    location_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    geography: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Location name cannot be blank.")
        return v.strip()


class WorldProp(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    prop_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    significance: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Prop name cannot be blank.")
        return v.strip()


class WorldBibleAggregate(BaseModel):
    """Mutable world bible owning the series world rules."""

    model_config = ConfigDict(frozen=True, extra="allow")

    series_id: str = Field(min_length=1)
    setting: str = Field(min_length=1)
    locations: tuple[WorldLocation, ...] = Field(default_factory=tuple)
    props: tuple[WorldProp, ...] = Field(default_factory=tuple)
    rules: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("setting")
    @classmethod
    def _setting_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("World setting cannot be blank.")
        return v.strip()

    def with_location(self, location: WorldLocation) -> WorldBibleAggregate:
        for existing in self.locations:
            if existing.location_id == location.location_id:
                return self
        return self.model_copy(
            update={
                "locations": (*self.locations, location),
                "updated_at": utc_now(),
                "optimistic_version": self.optimistic_version + 1,
            }
        )

    def with_prop(self, prop: WorldProp) -> WorldBibleAggregate:
        for existing in self.props:
            if existing.prop_id == prop.prop_id:
                return self
        return self.model_copy(
            update={
                "props": (*self.props, prop),
                "updated_at": utc_now(),
                "optimistic_version": self.optimistic_version + 1,
            }
        )


__all__ = ["WorldBibleAggregate", "WorldLocation", "WorldProp", "utc_now"]
