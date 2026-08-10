"""
Canonical Studio ports and authority contract (studio.contract/v0.1).

The frozen port set is shared by Plans A, B, and C
(docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/ports_and_authority.json).
Authority rules:
- API application services call ``StudioRunOrchestratorPort``; they do not
  construct a DAG or submit individual model tasks directly.
- ``OrchestratorService`` creates/advances the Story DAG and uses
  ``StudioTaskSubmissionPort`` for durable nodes.
- Worker runtime handlers execute one frozen task type, persist artifacts through
  ports/UoW, and return ``StudioTaskResult``.
- Durable completion is reconciled back into the orchestrator before the next
  dependent node becomes runnable.
- ``WorkflowEngine`` and ``ProductionWorkflowEngine`` receive no new Story
  imports, task types, states, or routes.
"""

from __future__ import annotations

from typing import Any, Awaitable, Dict, List, Optional, Protocol, TYPE_CHECKING, runtime_checkable

from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.contracts.studio.models import (
    StudioArtifactRef,
    StudioEventEnvelope,
    StudioRouteProvenance,
    StudioTaskEnvelope,
    StudioTaskResult,
)
from windagent_core.domain.video_production.ids import VideoProjectId  # noqa: F401

if TYPE_CHECKING:  # annotation-only; structural protocols stay runtime-free
    from windagent_core.domain.studio.series import SeriesProject
    from windagent_core.domain.studio.episode import Episode
    from windagent_core.domain.studio.revision import StudioProductionRevision
    from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
    from windagent_core.domain.studio.approval import ApprovalPolicy, StudioApprovalDecision
    from windagent_core.contracts.studio.capabilities import RuntimeCapabilityProfile


@runtime_checkable
class SeriesProjectRepositoryPort(Protocol):
    """Persistence port for the canonical SeriesProject aggregate."""

    async def get(self, series_id: SeriesProjectId) -> Optional["SeriesProject"]: ...

    async def save(self, project: "SeriesProject") -> "SeriesProject": ...

    async def list(self, cursor: Optional[str] = None, limit: int = 100) -> List["SeriesProject"]: ...


@runtime_checkable
class EpisodeRepositoryPort(Protocol):
    """Persistence port for the creative Episode aggregate."""

    async def get(self, episode_id: EpisodeId) -> Optional["Episode"]: ...

    async def save(self, episode: "Episode") -> "Episode": ...

    async def list_by_series(self, series_id: SeriesProjectId) -> List["Episode"]: ...


@runtime_checkable
class ProductionRevisionRepositoryPort(Protocol):
    """Extended compatible surface for the immutable revision lineage."""

    async def get(self, revision_id: ProductionRevisionId) -> Optional["StudioProductionRevision"]: ...

    async def save(self, revision: "StudioProductionRevision") -> "StudioProductionRevision": ...

    async def latest_for_episode(self, episode_id: EpisodeId) -> Optional["StudioProductionRevision"]: ...


@runtime_checkable
class StoryArtifactRepositoryPort(Protocol):
    """Persistence port for immutable story artifact envelopes."""

    async def get(self, artifact_id: ArtifactId) -> Optional["StoryArtifactEnvelope"]: ...

    async def save(self, artifact: "StoryArtifactEnvelope") -> "StoryArtifactEnvelope": ...

    async def find_by_hash(self, content_hash: str) -> Optional["StoryArtifactEnvelope"]: ...

    async def list_for_episode(self, episode_id: EpisodeId) -> List["StoryArtifactEnvelope"]: ...


@runtime_checkable
class ApprovalRepositoryPort(Protocol):
    """Persistence port for approval policies and decisions."""

    async def get_policy(
        self, policy_id: str, policy_version: Optional[str] = None
    ) -> Optional["ApprovalPolicy"]: ...

    async def save_policy(self, policy: "ApprovalPolicy") -> "ApprovalPolicy": ...

    async def record_decision(self, decision: "StudioApprovalDecision") -> "StudioApprovalDecision": ...

    async def decisions_for_revision(
        self, revision_id: ProductionRevisionId
    ) -> List["StudioApprovalDecision"]: ...


@runtime_checkable
class StudioUnitOfWorkPort(Protocol):
    """Transactional boundary uniting Studio repositories, outbox, and events."""

    series: SeriesProjectRepositoryPort
    episodes: EpisodeRepositoryPort
    revisions: ProductionRevisionRepositoryPort
    artifacts: StoryArtifactRepositoryPort
    approvals: ApprovalRepositoryPort

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def append_event(self, event: StudioEventEnvelope) -> None: ...

    async def publish_outbox(self, event: StudioEventEnvelope) -> None: ...


@runtime_checkable
class StudioRunOrchestratorPort(Protocol):
    """Sole new Story orchestration authority surfaced to application services."""

    async def create_series(self, command: Any) -> Any: ...

    async def create_episode(self, command: Any) -> Any: ...

    async def start_or_resume_run(self, command: Any) -> Any: ...

    async def select_idea(self, command: Any) -> Any: ...

    async def record_approval(self, command: Any) -> Any: ...

    async def derive_revision(self, command: Any) -> Any: ...

    async def lock_screenplay(self, command: Any) -> Any: ...

    async def cancel_run(self, run_id: StudioRunId, actor: str, reason: str = "") -> Any: ...


@runtime_checkable
class StudioTaskSubmissionPort(Protocol):
    """Durable queue submission for frozen Studio task envelopes."""

    async def submit(self, envelope: StudioTaskEnvelope) -> str: ...

    async def is_duplicate(self, idempotency_key: str) -> bool: ...


@runtime_checkable
class StudioRunQueryPort(Protocol):
    """Read model for run/DAG/task progress."""

    async def get_run(self, run_id: StudioRunId) -> Optional[Dict[str, Any]]: ...

    async def get_run_tasks(self, run_id: StudioRunId) -> List[Dict[str, Any]]: ...


@runtime_checkable
class StudioEventQueryPort(Protocol):
    """Canonical event stream/read-model query surface."""

    async def events_after(
        self, run_id: StudioRunId, after_sequence: int = 0, limit: int = 100
    ) -> List[StudioEventEnvelope]: ...

    async def latest_sequence(self, run_id: StudioRunId) -> int: ...


@runtime_checkable
class RuntimeCapabilityPort(Protocol):
    """Typed runtime readiness query; fails closed on fake/mock/bypass."""

    async def get_capabilities(self) -> "RuntimeCapabilityProfile": ...


@runtime_checkable
class PreproductionModelPort(Protocol):
    """Provider-neutral preproduction model boundary backed by route lock."""

    async def execute(self, request: Any, *, route_lock_id: Optional[str] = None) -> Any: ...

    async def lock_route(self, request: Any) -> "StudioRouteLockResult": ...


class StudioRouteLockResult(Protocol):
    """Returned by a real model route lock; carries provenance."""

    route_lock_id: Optional[str]
    provenance: StudioRouteProvenance
    prompt_ref: Optional[Dict[str, str]]


__all__ = [
    "SeriesProjectRepositoryPort",
    "EpisodeRepositoryPort",
    "ProductionRevisionRepositoryPort",
    "StoryArtifactRepositoryPort",
    "ApprovalRepositoryPort",
    "StudioUnitOfWorkPort",
    "StudioRunOrchestratorPort",
    "StudioTaskSubmissionPort",
    "StudioRunQueryPort",
    "StudioEventQueryPort",
    "RuntimeCapabilityPort",
    "PreproductionModelPort",
    "StudioRouteLockResult",
]
