"""
Location, Prop, and Style bibles — canonical setting entities.

Each aggregate references assets by stable ID and carries visual/lighting
metadata used by the Director layer (road_map.md Phase 6 / Phase 7).
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import (
    LocationId,
    PropId,
    ReferenceAssetId,
    StyleBibleId,
)


class LocationBible(BaseModel):
    """Canonical location definition."""

    model_config = ConfigDict(frozen=True, extra="allow")

    location_id: LocationId
    name: str = Field(min_length=1)
    visual_description: str = ""
    lighting_profile: str = ""
    atmosphere_tags: List[str] = Field(default_factory=list)
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PropBible(BaseModel):
    """Canonical prop definition."""

    model_config = ConfigDict(frozen=True, extra="allow")

    prop_id: PropId
    name: str = Field(min_length=1)
    description: str = ""
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StyleBible(BaseModel):
    """Canonical visual style definition."""

    model_config = ConfigDict(frozen=True, extra="allow")

    style_id: StyleBibleId
    name: str = Field(min_length=1)
    visual_style: str = ""
    color_palette: List[str] = Field(default_factory=list)
    lighting_rules: List[str] = Field(default_factory=list)
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["LocationBible", "PropBible", "StyleBible"]
