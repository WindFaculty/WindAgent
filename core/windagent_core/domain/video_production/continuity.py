"""
Continuity ledger state for a shot (road_map.md Phase 10).

Tracks identity, costume, props, lighting, weather, time, camera side,
180-degree rule, and scene geography across shots and scenes.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import ContinuityStateId, ShotId


class ContinuityState(BaseModel):
    """Per-shot continuity snapshot."""

    model_config = ConfigDict(frozen=True, extra="allow")

    state_id: ContinuityStateId
    shot_id: ShotId
    character_states: Dict[str, Any] = Field(default_factory=dict)
    location_state: Dict[str, Any] = Field(default_factory=dict)
    prop_states: Dict[str, Any] = Field(default_factory=dict)
    camera_state: Dict[str, Any] = Field(default_factory=dict)
    must_preserve: List[str] = Field(default_factory=list)
    allowed_changes: List[str] = Field(default_factory=list)


__all__ = ["ContinuityState"]
