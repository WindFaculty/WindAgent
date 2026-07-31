"""
Scene entity for the video production domain.

Scenes carry an explicit `order` integer (never derived from display names)
and reference characters, locations, and dialogue lines by stable ID.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import TimeOfDay
from windagent_core.domain.video_production.ids import (
    CharacterId,
    DialogueLineId,
    LocationId,
    SceneId,
)


class Scene(BaseModel):
    """A screenplay scene with explicit ordering."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: SceneId
    order: int = Field(ge=1)
    title: str = ""
    location_id: LocationId
    character_ids: List[CharacterId] = Field(default_factory=list)
    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    action_description: str = ""
    time_of_day: Optional[TimeOfDay] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["Scene"]
