"""
Canonical Studio ``SeriesProject`` aggregate (studio.contract/v0.1).

Canonical hierarchy is exactly ``SeriesProject -> Episode -> ProductionRevision``.
``VideoProject`` remains a V2 compatibility facade/read path during deprecation;
it is not a competing aggregate (see ``domain/studio/compat.py`` for the explicit,
lossless conversion).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId
from windagent_core.contracts.studio.errors import StudioValidationError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SeriesProject(BaseModel):
    """Top-level canonical Studio aggregate owning creative episodes."""

    model_config = ConfigDict(frozen=True, extra="allow")

    series_id: SeriesProjectId
    title: str = Field(min_length=1)
    description: str = ""
    episode_ids: tuple[EpisodeId, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("SeriesProject title cannot be blank.")
        return v.strip()

    def with_episode(self, episode_id: EpisodeId) -> SeriesProject:
        """Return an immutable copy with a newly attached episode."""
        if episode_id in self.episode_ids:
            return self
        return self.model_copy(
            update={
                "episode_ids": (*self.episode_ids, episode_id),
                "updated_at": utc_now(),
            }
        )


__all__ = ["utc_now", "SeriesProject"]
