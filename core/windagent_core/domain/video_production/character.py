"""
CharacterBible aggregate — canonical identity reference for a character.

References canonical portrait assets by ID; the catalog maps one character
to a stable identity across shots (road_map.md DIR-REQ-003).
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import CharacterRole
from windagent_core.domain.video_production.ids import (
    CharacterId,
    ReferenceAssetId,
)


class CharacterBible(BaseModel):
    """Canonical identity reference catalog entry for a character."""

    model_config = ConfigDict(frozen=True, extra="allow")

    character_id: CharacterId
    name: str = Field(min_length=1)
    role: CharacterRole = CharacterRole.SUPPORTING
    visual_traits: Dict[str, str] = Field(default_factory=dict)
    costume_descriptions: List[str] = Field(default_factory=list)
    portrait_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["CharacterBible"]
