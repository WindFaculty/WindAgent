"""
V3 Studio request/response schemas (Plan C1).

Request models reuse the frozen Plan A command models; only the idempotency
key moves to the ``X-Idempotency-Key`` header (enforced by dependencies), so
there is a single source of truth for command fields and validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    DeriveRevisionCommand,
    LockScreenplayCommand,
    RecordApprovalCommand,
    SelectIdeaCommand,
    UpdateEpisodeCommand,
)
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, SeriesProjectId, StudioRunId


class CreateSeriesRequest(CreateSeriesCommand):
    idempotency_key: Optional[str] = None


class CreateEpisodeRequest(CreateEpisodeCommand):
    idempotency_key: Optional[str] = None


class UpdateSeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    metadata_patch: Dict[str, Any] = Field(default_factory=dict)


class UpdateEpisodeRequest(UpdateEpisodeCommand):
    idempotency_key: Optional[str] = None


class PreflightCheckResource(BaseModel):
    name: str
    status: str
    detail: str = ""


class PreflightReportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: str
    ready: bool
    checks: List[PreflightCheckResource] = Field(default_factory=list)


class StartRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "studio.command/v1"


class SelectIdeaRequest(SelectIdeaCommand):
    idempotency_key: Optional[str] = None


class RecordApprovalRequest(RecordApprovalCommand):
    idempotency_key: Optional[str] = None
    # Actor comes from the X-WindAgent-Actor header, not the body.
    actor: Optional[str] = None


class DeriveRevisionRequest(DeriveRevisionCommand):
    idempotency_key: Optional[str] = None
    actor: Optional[str] = None


class LockScreenplayRequest(LockScreenplayCommand):
    idempotency_key: Optional[str] = None


class SeriesListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: List[Dict[str, Any]] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class EpisodeListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: List[Dict[str, Any]] = Field(default_factory=list)


class ArtifactListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: List[Dict[str, Any]] = Field(default_factory=list)
    episode_id: Optional[str] = None


class RunEventsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    after_sequence: int
    latest_sequence: int
    events: List[Dict[str, Any]] = Field(default_factory=list)


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    capabilities: Dict[str, str]
    fail_closed_flags: List[str] = Field(default_factory=list)
    certification_mode: bool = False


__all__ = [
    "CreateSeriesRequest",
    "CreateEpisodeRequest",
    "UpdateSeriesRequest",
    "UpdateEpisodeRequest",
    "PreflightCheckResource",
    "PreflightReportResponse",
    "StartRunRequest",
    "SelectIdeaRequest",
    "RecordApprovalRequest",
    "DeriveRevisionRequest",
    "LockScreenplayRequest",
    "SeriesListResponse",
    "EpisodeListResponse",
    "ArtifactListResponse",
    "RunEventsResponse",
    "ReadinessResponse",
    "SeriesProjectId",
    "EpisodeId",
    "StudioRunId",
    "ArtifactId",
]
