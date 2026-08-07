"""
Legacy compatibility — `LegacyGenerationRequest`.

The canonical `GenerationRequest` (generation_job.py) dropped its
`generation_mode` field during VP3D Stage A; the old request shape is kept
HERE so the bounded legacy reader (`ProductionIrMigrator`) and legacy fixture
tests can still read/migrate artifacts written before the cutover.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import (
    GenerationRequestId,
    ProductionRevisionId,
    ShotId,
    VideoProjectId,
)
from windagent_core.domain.video_production.legacy_v1.enums import GenerationMode


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyGenerationRequest(BaseModel):
    """Legacy idempotent generative-video request (retired in Stage A)."""

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


__all__ = ["LegacyGenerationRequest", "utc_now"]
