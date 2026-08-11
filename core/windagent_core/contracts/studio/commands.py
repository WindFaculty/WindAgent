"""
Canonical Studio application command/result contracts (studio.contract/v0.1).

These are the application-facing commands an API layer may send to the Studio
authority (``StudioRunOrchestratorPort``). They never build a DAG and never
submit model tasks directly. Mutating commands carry an idempotency key and the
expected revision/version where applicable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.contracts.studio.ids import (
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)

COMMAND_SCHEMA_VERSION = "studio.command/v1"


class StudioCommand(BaseModel):
    """Base command; carries the versioned contract discriminator."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = COMMAND_SCHEMA_VERSION
    idempotency_key: str = Field(min_length=1)


class CreateSeriesCommand(StudioCommand):
    title: str = Field(min_length=1)
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateSeriesResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    series_id: SeriesProjectId
    title: str


class CreateEpisodeCommand(StudioCommand):
    series_id: SeriesProjectId
    title: str = Field(min_length=1)
    episode_number: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateEpisodeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: EpisodeId
    series_id: SeriesProjectId
    state: str


class StartRunCommand(StudioCommand):
    """Idempotently ask the orchestrator to start or resume a Story DAG."""

    episode_id: EpisodeId


class StartRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: StudioRunId
    episode_id: EpisodeId
    resuming: bool = False


class SelectIdeaCommand(StudioCommand):
    """Bind a selected idea candidate to a revision/hash (synchronous/idempotent)."""

    episode_id: EpisodeId
    revision_id: ProductionRevisionId
    candidate_id: str = Field(min_length=1)
    expected_content_hash: str = Field(min_length=64, max_length=64)
    expected_optimistic_version: Optional[int] = None


class SelectIdeaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: EpisodeId
    candidate_id: str
    revision_id: ProductionRevisionId
    content_hash: str = Field(min_length=64, max_length=64)
    optimistic_version: int = Field(ge=1)
    replayed: bool = False


class RecordApprovalCommand(StudioCommand):
    """Bind an approval decision to a checkpoint/revision/artifact hash."""

    episode_id: EpisodeId
    revision_id: ProductionRevisionId
    checkpoint: str = Field(min_length=1)
    artifact_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    reason: str = ""
    expected_optimistic_version: Optional[int] = None


class RecordApprovalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: EpisodeId
    checkpoint: str
    next_state: Optional[str] = None
    awaiting_approval: bool = False


class DeriveRevisionCommand(StudioCommand):
    """Derive a new revision from a locked or current revision."""

    episode_id: EpisodeId
    series_id: SeriesProjectId
    parent_revision_id: ProductionRevisionId
    new_content_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1)
    invalidation_intent: Optional[str] = None
    summary: str = ""
    expected_optimistic_version: Optional[int] = None


class DeriveRevisionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision_id: ProductionRevisionId
    parent_revision_id: ProductionRevisionId
    episode_id: EpisodeId


class LockScreenplayCommand(StudioCommand):
    """Idempotent screenplay lock for an episode."""

    episode_id: EpisodeId
    revision_id: ProductionRevisionId
    expected_content_hash: str = Field(min_length=64, max_length=64)
    expected_optimistic_version: Optional[int] = None


class LockScreenplayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: EpisodeId
    revision_id: ProductionRevisionId
    lock_receipt_artifact_id: Optional[str] = None
    state: str


__all__ = [
    "COMMAND_SCHEMA_VERSION",
    "StudioCommand",
    "CreateSeriesCommand",
    "CreateSeriesResult",
    "CreateEpisodeCommand",
    "CreateEpisodeResult",
    "StartRunCommand",
    "StartRunResult",
    "SelectIdeaCommand",
    "SelectIdeaResult",
    "RecordApprovalCommand",
    "RecordApprovalResult",
    "DeriveRevisionCommand",
    "DeriveRevisionResult",
    "LockScreenplayCommand",
    "LockScreenplayResult",
]
