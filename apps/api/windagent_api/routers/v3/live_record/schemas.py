"""Live Record V3 request/response schemas (snake_case JSON)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreatePlanRequest(BaseModel):
    episode_id: str = Field(min_length=1)
    episode_revision_id: str = Field(min_length=1)
    scenes: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    recording_profile: Optional[Dict[str, Any]] = None
    # Prepared payload bundles keyed by action_id — exact artifact content map
    # (Section 6). Never inline in tool args, only via artifact:// payload_ref.
    payload_bundles: Optional[Dict[str, str]] = None


class PatchPlanContentRequest(BaseModel):
    scenes: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    payload_bundles: Optional[Dict[str, str]] = None
    source_workspace_hash: Optional[str] = None


class TransitionPlanRequest(BaseModel):
    """Body for lifecycle transitions; ``current_episode_revision_id`` is only
    required by ``check`` (staleness assertion) but accepted on any command so
    callers can assert freshness in the same round trip."""

    current_episode_revision_id: Optional[str] = None


class CreateTakeRequest(BaseModel):
    pass


class AppendEventRequest(BaseModel):
    event_type: str = Field(min_length=1)
    t: float = Field(default=0.0, ge=0)
    scene_id: Optional[str] = None
    cue_id: Optional[str] = None
    action_id: Optional[str] = None
    segment_id: Optional[str] = None
    execution_id: Optional[str] = None
    marker_type: Optional[str] = None
    detail: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class PlanListResponse(BaseModel):
    items: List[Dict[str, Any]]


class TakeListResponse(BaseModel):
    items: List[Dict[str, Any]]

class EventListResponse(BaseModel):
    items: List[Dict[str, Any]]


__all__ = [
    "CreatePlanRequest",
    "PatchPlanContentRequest",
    "TransitionPlanRequest",
    "CreateTakeRequest",
    "AppendEventRequest",
    "PlanListResponse",
    "TakeListResponse",
    "EventListResponse",
]
