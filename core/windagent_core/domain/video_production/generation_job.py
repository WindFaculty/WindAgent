"""
Generation job models: GenerationRequest, GenerationCandidate, and the
aggregated GenerationRecord.

Every generated candidate must be traceable back to its request hash, prompt
version, reference hashes, provider, and generation parameters
(road_map.md Phase 15 / Phase 18 content addressing).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import GenerationMode, GenerationStatus
from windagent_core.domain.video_production.ids import (
    GenerationCandidateId,
    GenerationRequestId,
    ProductionRevisionId,
    ReviewResultId,
    ShotId,
    VideoProjectId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationRequest(BaseModel):
    """Idempotent request to a media generation provider."""

    model_config = ConfigDict(frozen=True, extra="allow")

    request_id: GenerationRequestId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    shot_id: ShotId
    generation_mode: GenerationMode
    provider: str = ""
    prompt_version: str = "1.0.0"
    prompt_hash: str = Field(min_length=64, max_length=64)
    reference_hashes: List[str] = Field(default_factory=list)
    request_hash: str = Field(min_length=64, max_length=64)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=utc_now)


class GenerationCandidate(BaseModel):
    """One candidate output from a provider, traceable to its request."""

    model_config = ConfigDict(frozen=True, extra="allow")

    candidate_id: GenerationCandidateId
    request_id: GenerationRequestId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    shot_id: ShotId
    request_hash: str = Field(min_length=64, max_length=64)
    prompt_version: str = "1.0.0"
    reference_hashes: List[str] = Field(default_factory=list)
    provider: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: GenerationStatus = GenerationStatus.SUBMITTED
    content_hash: Optional[str] = None
    media_uri: str = ""
    review_result_id: Optional[ReviewResultId] = None
    created_at: datetime = Field(default_factory=utc_now)


class GenerationRecord(BaseModel):
    """Aggregated record: request + candidates + selected result."""

    model_config = ConfigDict(frozen=True, extra="allow")

    request: GenerationRequest
    candidates: List[GenerationCandidate] = Field(default_factory=list)
    selected_candidate_id: Optional[GenerationCandidateId] = None
    status: GenerationStatus = GenerationStatus.SUBMITTED
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "utc_now",
    "GenerationRequest",
    "GenerationCandidate",
    "GenerationRecord",
]
