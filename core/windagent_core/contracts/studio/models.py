"""
Canonical Studio durable-task envelope models (studio.contract/v0.1).

These models are the durable boundary between the orchestrator, the queue, and
the worker. They are intentionally storage- and provider-neutral; Plan B
supplies handler payload schemas and Plan C consumes the serialized shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.events.studio import (
    StudioEventEnvelope,  # noqa: F401 — single canonical event envelope
)

CONTRACT_VERSION = "studio.contract/v0.1"
TASK_ENVELOPE_SCHEMA_VERSION = "studio.task_envelope/v1"
TASK_RESULT_SCHEMA_VERSION = "studio.task_result/v1"
EVENT_SCHEMA_VERSION = "studio.event/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudioTaskStatus(str, Enum):
    """Durable task lifecycle status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StudioNodeStatus(str, Enum):
    """Durable orchestrator node lifecycle status (Plan A — A4).

    PENDING: dependencies not yet terminal.
    RUNNABLE: dependencies terminal; ready for durable submission.
    DISPATCHED: a durable task identity is committed for this node.
    SUCCEEDED: terminal success (directly, or after an approval gate passed).
    FAILED: terminal failure (retry budget exhausted or approval rejected).
    CANCELLED: terminal cancellation (run cancelled or superseded).
    SKIPPED: terminal branch bypass; no task was submitted or completed.
    WAITING_APPROVAL: durable approval-gate wait; only approval resumes it.
    """

    PENDING = "PENDING"
    RUNNABLE = "RUNNABLE"
    DISPATCHED = "DISPATCHED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    WAITING_APPROVAL = "WAITING_APPROVAL"

    @classmethod
    def terminal(cls) -> frozenset[str]:
        return frozenset(
            {cls.SUCCEEDED.value, cls.FAILED.value, cls.CANCELLED.value, cls.SKIPPED.value}
        )


class StudioTaskType(str, Enum):
    """Frozen durable Studio task types (studio.contract/v0.1)."""

    IDEA_GENERATE = "studio.story.idea.generate"
    IDEA_EVALUATE = "studio.story.idea.evaluate"
    BIBLE_GENERATE = "studio.story.bible.generate"
    BEATS_GENERATE = "studio.story.beats.generate"
    OUTLINE_GENERATE = "studio.story.outline.generate"
    SCREENPLAY_GENERATE = "studio.story.screenplay.generate"
    REVIEW = "studio.story.review"
    REVISE = "studio.story.revise"
    LOCK = "studio.story.lock"


class StudioArtifactRef(BaseModel):
    """Reference to an immutable story artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: ArtifactId
    artifact_type: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    schema_version: str = "studio.artifact/v1alpha1"


class StudioRouteProvenance(BaseModel):
    """Route/model provider provenance attached to a task result."""

    model_config = ConfigDict(frozen=True, extra="allow")

    model_route_id: Optional[str] = None
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    canonical_model_id: Optional[str] = None
    provider_model_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    provider_binding_id: Optional[str] = None
    provider_attempt_id: Optional[str] = None
    provider_request_id: Optional[str] = None
    output_schema_contract: Optional[str] = None
    prompt_id: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt_hash: Optional[str] = None
    usage: Dict[str, Any] = Field(default_factory=dict)


class StudioTaskEnvelope(BaseModel):
    """Durable, versioned envelope for a single frozen Studio story task."""

    model_config = ConfigDict(frozen=True, extra="allow")

    contract_version: str = CONTRACT_VERSION
    schema_version: str = TASK_ENVELOPE_SCHEMA_VERSION
    task_type: StudioTaskType
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    studio_run_id: StudioRunId
    dag_node_id: str = Field(min_length=1)
    series_id: SeriesProjectId
    episode_id: EpisodeId
    revision_id: Optional[ProductionRevisionId] = None
    input_artifact_refs: List[StudioArtifactRef] = Field(default_factory=list)
    input_hashes: List[str] = Field(default_factory=list)
    approval_policy_id: Optional[str] = None
    approval_policy_version: Optional[str] = None
    idempotency_key: str = Field(min_length=1)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: Optional[str] = None
    attempt: int = Field(default=1, ge=1)
    deadline: Optional[datetime] = None
    requested_capabilities: List[str] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class StudioTaskResult(BaseModel):
    """Result of a Studio task execution, returned to the finalizer/reconciler."""

    model_config = ConfigDict(frozen=True, extra="allow")

    contract_version: str = CONTRACT_VERSION
    schema_version: str = TASK_RESULT_SCHEMA_VERSION
    task_id: str = Field(min_length=1)
    studio_run_id: StudioRunId
    dag_node_id: str = Field(min_length=1)
    status: StudioTaskStatus = StudioTaskStatus.SUCCEEDED
    output_artifact_refs: List[StudioArtifactRef] = Field(default_factory=list)
    output_hashes: List[str] = Field(default_factory=list)
    quality_summary: Optional[str] = None
    route_provenance: Optional[StudioRouteProvenance] = None
    usage: Dict[str, Any] = Field(default_factory=dict)
    next_episode_state: Optional[str] = None
    emitted_event_refs: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    @model_validator(mode="after")
    def _check_error_status(self) -> StudioTaskResult:
        if self.status == StudioTaskStatus.SUCCEEDED and self.error:
            raise ValueError("A succeeded StudioTaskResult cannot carry an error.")
        if (
            self.status in (StudioTaskStatus.FAILED, StudioTaskStatus.CANCELLED)
            and not self.error
        ):
            raise ValueError(f"A {self.status.value} StudioTaskResult must carry an error.")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "CONTRACT_VERSION",
    "TASK_ENVELOPE_SCHEMA_VERSION",
    "TASK_RESULT_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "utc_now",
    "StudioTaskStatus",
    "StudioNodeStatus",
    "StudioTaskType",
    "StudioArtifactRef",
    "StudioRouteProvenance",
    "StudioTaskEnvelope",
    "StudioTaskResult",
    "StudioEventEnvelope",
]
