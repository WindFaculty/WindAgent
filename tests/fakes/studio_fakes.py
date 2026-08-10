"""
Plan C1 test doubles implementing the frozen Plan A Studio ports.

These live in the explicit test namespace (tests/fakes) and are NEVER imported
by production code. They emulate the Plan A authority semantics that the V3
contract tests must observe: idempotent replay/mismatch, optimistic version
conflicts, artifact hash mismatches, locked revisions, and durable run/event
read models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapability,
    RuntimeCapabilityProfile,
)
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateEpisodeResult,
    CreateSeriesCommand,
    CreateSeriesResult,
    DeriveRevisionCommand,
    DeriveRevisionResult,
    LockScreenplayCommand,
    LockScreenplayResult,
    RecordApprovalCommand,
    RecordApprovalResult,
    SelectIdeaCommand,
    SelectIdeaResult,
    StartRunCommand,
    StartRunResult,
)
from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioIdempotencyMismatchError,
    StudioLockedRevisionError,
    StudioNotFoundError,
    StudioStaleRevisionError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.domain.studio.approval import ApprovalDecisionValue, StudioApprovalDecision
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.revision import (
    StudioLockState,
    StudioProductionRevision,
    StudioRevisionStatus,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.events.studio import StudioEventEnvelope


class _IdempotencyMixin:
    """Frozen idempotency rule: same key + same normalized request replays the
    original result; same key + different request raises IDEMPOTENCY_MISMATCH."""

    def __init__(self) -> None:
        self._idem: Dict[str, Dict[str, Any]] = {}

    def _replay(self, command: Any, result: Any) -> Any:
        key = command.idempotency_key
        normalized = command.model_dump(exclude={"idempotency_key"})
        prior = self._idem.get(key)
        if prior is None:
            self._idem[key] = {"request": normalized, "result": result}
            return result
        if prior["request"] != normalized:
            raise StudioIdempotencyMismatchError(
                "Repeated idempotency key used with a different normalized request.",
                details={"idempotency_key": key},
            )
        return prior["result"]


class FakeStudioOrchestrator(_IdempotencyMixin):
    """In-memory Plan A authority double for V3 contract tests."""

    def __init__(self) -> None:
        super().__init__()
        self._series: Dict[str, SeriesProject] = {}
        self._episodes: Dict[str, Episode] = {}
        self._revisions: Dict[str, StudioProductionRevision] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, List[StudioEventEnvelope]] = {}
        self._decisions: List[StudioApprovalDecision] = []
        self._selected: Dict[str, str] = {}  # episode_id -> candidate_id
        self._counters = {"series": 0, "episode": 0, "run": 0, "revision": 0}
        self.idea_hash = "a" * 64

    # -- commands ----------------------------------------------------------

    async def create_series(self, command: CreateSeriesCommand) -> CreateSeriesResult:
        self._counters["series"] += 1
        series = SeriesProject(
            series_id=SeriesProjectId(f"series_{self._counters['series']:04d}"),
            title=command.title,
            description=command.description,
            metadata=command.metadata,
        )
        result = CreateSeriesResult(series_id=series.series_id, title=series.title)
        replayed = self._replay(command, result)
        self._series[str(series.series_id)] = series
        return replayed

    async def create_episode(self, command: CreateEpisodeCommand) -> CreateEpisodeResult:
        self._counters["episode"] += 1
        episode = Episode(
            episode_id=EpisodeId(f"episode_{self._counters['episode']:04d}"),
            series_id=command.series_id,
            title=command.title,
            episode_number=command.episode_number,
            metadata=command.metadata,
        )
        result = CreateEpisodeResult(
            episode_id=episode.episode_id, series_id=episode.series_id, state=episode.state.value
        )
        replayed = self._replay(command, result)
        self._episodes[str(episode.episode_id)] = episode
        return replayed

    async def start_or_resume_run(self, command: StartRunCommand) -> StartRunResult:
        episode = self._episodes.get(str(command.episode_id))
        if episode is None:
            raise StudioNotFoundError("Episode does not exist.", details={"episode_id": str(command.episode_id)})
        self._counters["run"] += 1
        run_id = StudioRunId(f"run_{self._counters['run']:04d}")
        self._runs[str(run_id)] = {
            "run_id": str(run_id),
            "episode_id": str(command.episode_id),
            "status": "RUNNING",
            "dag": [
                {"node_id": "idea_generate", "status": "RUNNING"},
                {"node_id": "idea_evaluate", "status": "PENDING"},
            ],
            "tasks": [],
            "wait_reason": None,
            "retryable": False,
            "latest_sequence": 0,
        }
        result = StartRunResult(run_id=run_id, episode_id=command.episode_id, resuming=False)
        return self._replay(command, result)

    async def select_idea(self, command: SelectIdeaCommand) -> SelectIdeaResult:
        episode = self._episodes.get(str(command.episode_id))
        if episode is None:
            raise StudioNotFoundError("Episode does not exist.", details={"episode_id": str(command.episode_id)})
        if command.expected_content_hash != self.idea_hash:
            raise StudioArtifactHashMismatchError(
                "Artifact content hash does not match the expected canonical hash.",
                details={
                    "episode_id": str(command.episode_id),
                    "expected": command.expected_content_hash,
                    "current": self.idea_hash,
                },
            )
        if command.expected_optimistic_version is not None and (
            command.expected_optimistic_version != episode.optimistic_version
        ):
            raise StudioStaleRevisionError(
                "Optimistic version mismatch; episode changed since it was read.",
                details={
                    "expected_version": command.expected_optimistic_version,
                    "current_version": episode.optimistic_version,
                },
            )
        result = SelectIdeaResult(
            episode_id=command.episode_id,
            candidate_id=command.candidate_id,
            revision_id=command.revision_id,
        )
        replayed = self._replay(command, result)
        self._selected[str(command.episode_id)] = command.candidate_id
        return replayed

    async def record_approval(self, command: RecordApprovalCommand) -> RecordApprovalResult:
        episode = self._episodes.get(str(command.episode_id))
        if episode is None:
            raise StudioNotFoundError("Episode does not exist.", details={"episode_id": str(command.episode_id)})
        if command.expected_optimistic_version is not None and (
            command.expected_optimistic_version != episode.optimistic_version
        ):
            raise StudioStaleRevisionError(
                "Optimistic version mismatch; episode changed since it was read.",
                details={
                    "expected_version": command.expected_optimistic_version,
                    "current_version": episode.optimistic_version,
                },
            )
        decision = ApprovalDecisionValue(command.decision)
        awaiting = decision == ApprovalDecisionValue.REJECTED
        result = RecordApprovalResult(
            episode_id=command.episode_id,
            checkpoint=command.checkpoint,
            next_state="REVISING" if awaiting else None,
            awaiting_approval=awaiting,
        )
        replayed = self._replay(command, result)
        self._decisions.append(
            StudioApprovalDecision(
                approval_id=f"approval_{len(self._decisions) + 1:04d}",
                aggregate_id=command.episode_id,
                revision_id=command.revision_id,
                artifact_hash=command.artifact_hash,
                checkpoint=command.checkpoint,
                actor=command.actor,
                decision=decision,
                reason=command.reason,
            )
        )
        return replayed

    async def derive_revision(self, command: DeriveRevisionCommand) -> DeriveRevisionResult:
        parent = self._revisions.get(str(command.parent_revision_id))
        if parent is not None and parent.lock_state == StudioLockState.LOCKED:
            raise StudioLockedRevisionError(
                "Operation rejected because the revision is locked.",
                details={"revision_id": str(command.parent_revision_id)},
            )
        self._counters["revision"] += 1
        revision = StudioProductionRevision(
            revision_id=ProductionRevisionId(f"revision_{self._counters['revision']:04d}"),
            series_id=command.series_id,
            episode_id=command.episode_id,
            parent_revision_id=command.parent_revision_id,
            creator=command.actor,
            actor=command.actor,
            content_hash=command.new_content_hash,
            summary=command.summary,
        )
        result = DeriveRevisionResult(
            revision_id=revision.revision_id,
            parent_revision_id=command.parent_revision_id,
            episode_id=command.episode_id,
        )
        replayed = self._replay(command, result)
        self._revisions[str(revision.revision_id)] = revision
        episode = self._episodes.get(str(command.episode_id))
        if episode is not None:
            self._episodes[str(episode.episode_id)] = episode._bump(
                current_revision_id=revision.revision_id
            )
        return replayed

    async def lock_screenplay(self, command: LockScreenplayCommand) -> LockScreenplayResult:
        episode = self._episodes.get(str(command.episode_id))
        if episode is None:
            raise StudioNotFoundError("Episode does not exist.", details={"episode_id": str(command.episode_id)})
        revision = self._revisions.get(str(command.revision_id))
        if revision is not None and revision.lock_state == StudioLockState.LOCKED:
            if revision.content_hash != command.expected_content_hash:
                raise StudioLockedRevisionError(
                    "Operation rejected because the revision is locked.",
                    details={"revision_id": str(command.revision_id)},
                )
        if command.expected_content_hash != self.idea_hash:
            raise StudioArtifactHashMismatchError(
                "Artifact content hash does not match the expected canonical hash.",
                details={"expected": command.expected_content_hash, "current": self.idea_hash},
            )
        result = LockScreenplayResult(
            episode_id=command.episode_id,
            revision_id=command.revision_id,
            lock_receipt_artifact_id=f"artifact_lock_{len(self._revisions) + 1:04d}",
            state="LOCKED",
        )
        replayed = self._replay(command, result)
        if revision is not None:
            self._revisions[str(revision.revision_id)] = revision.model_copy(
                update={"lock_state": StudioLockState.LOCKED, "state": StudioRevisionStatus.LOCKED}
            )
        return replayed

    async def cancel_run(self, run_id: StudioRunId, actor: str, reason: str = "") -> Any:
        run = self._runs.get(str(run_id))
        if run is None:
            raise StudioNotFoundError("Run does not exist.", details={"run_id": str(run_id)})
        run["status"] = "CANCELLED"
        return {"run_id": str(run_id), "status": "CANCELLED"}


class FakeRunQueryPort:
    """In-memory StudioRunQueryPort double."""

    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get_run(self, run_id: StudioRunId) -> Optional[Dict[str, Any]]:
        return self._orchestrator._runs.get(str(run_id))

    async def get_run_tasks(self, run_id: StudioRunId) -> List[Dict[str, Any]]:
        run = self._orchestrator._runs.get(str(run_id), {})
        return list(run.get("tasks", []))


class FakeEventQueryPort:
    """In-memory StudioEventQueryPort double; envelopes seeded by tests."""

    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator
        self.events: List[StudioEventEnvelope] = []

    async def events_after(
        self, run_id: StudioRunId, after_sequence: int = 0, limit: int = 100
    ) -> List[StudioEventEnvelope]:
        return [e for e in self.events if e.sequence > after_sequence][:limit]

    async def latest_sequence(self, run_id: StudioRunId) -> int:
        return max((e.sequence for e in self.events), default=0)


class FakeSeriesRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, series_id: SeriesProjectId) -> Optional[SeriesProject]:
        return self._orchestrator._series.get(str(series_id))

    async def save(self, project: SeriesProject) -> SeriesProject:
        self._orchestrator._series[str(project.series_id)] = project
        return project

    async def list(self, cursor: Optional[str] = None, limit: int = 100) -> List[SeriesProject]:
        items = list(self._orchestrator._series.values())
        return items[:limit]


class FakeEpisodeRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, episode_id: EpisodeId) -> Optional[Episode]:
        return self._orchestrator._episodes.get(str(episode_id))

    async def save(self, episode: Episode) -> Episode:
        self._orchestrator._episodes[str(episode.episode_id)] = episode
        return episode

    async def list_by_series(self, series_id: SeriesProjectId) -> List[Episode]:
        return [e for e in self._orchestrator._episodes.values() if e.series_id == series_id]


class FakeRevisionRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, revision_id: ProductionRevisionId) -> Optional[StudioProductionRevision]:
        return self._orchestrator._revisions.get(str(revision_id))

    async def save(self, revision: StudioProductionRevision) -> StudioProductionRevision:
        self._orchestrator._revisions[str(revision.revision_id)] = revision
        return revision

    async def latest_for_episode(self, episode_id: EpisodeId) -> Optional[StudioProductionRevision]:
        for rev in self._orchestrator._revisions.values():
            if rev.episode_id == episode_id:
                return rev
        return None


class FakeArtifactRepository:
    def __init__(self) -> None:
        self.artifacts: Dict[str, StoryArtifactEnvelope] = {}

    async def get(self, artifact_id: ArtifactId) -> Optional[StoryArtifactEnvelope]:
        return self.artifacts.get(str(artifact_id))

    async def save(self, artifact: StoryArtifactEnvelope) -> StoryArtifactEnvelope:
        self.artifacts[str(artifact.artifact_id)] = artifact
        return artifact

    async def find_by_hash(self, content_hash: str) -> Optional[StoryArtifactEnvelope]:
        for artifact in self.artifacts.values():
            if artifact.content_hash == content_hash:
                return artifact
        return None

    async def list_for_episode(self, episode_id: EpisodeId) -> List[StoryArtifactEnvelope]:
        return [a for a in self.artifacts.values() if a.episode_id == episode_id]


class FakeApprovalRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get_policy(self, policy_id: str, policy_version: Optional[str] = None) -> Any:
        return None

    async def save_policy(self, policy: Any) -> Any:
        return policy

    async def record_decision(self, decision: StudioApprovalDecision) -> StudioApprovalDecision:
        self._orchestrator._decisions.append(decision)
        return decision

    async def decisions_for_revision(self, revision_id: ProductionRevisionId) -> List[StudioApprovalDecision]:
        return [d for d in self._orchestrator._decisions if d.revision_id == revision_id]


class FakeCapabilityPort:
    """Test capability port: everything available, nothing fail-closed."""

    async def get_capabilities(self) -> RuntimeCapabilityProfile:
        return RuntimeCapabilityProfile(
            capabilities=[
                RuntimeCapability(
                    name="durable_db", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
                RuntimeCapability(
                    name="studio_orchestration",
                    status=CapabilityStatus.AVAILABLE,
                    source="fake",
                    reason="test double",
                ),
                RuntimeCapability(
                    name="worker", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
                RuntimeCapability(
                    name="model_route", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
            ],
            fail_closed_flags=[],
            certification_mode=True,
        )


__all__ = [
    "FakeStudioOrchestrator",
    "FakeRunQueryPort",
    "FakeEventQueryPort",
    "FakeSeriesRepository",
    "FakeEpisodeRepository",
    "FakeRevisionRepository",
    "FakeArtifactRepository",
    "FakeApprovalRepository",
    "FakeCapabilityPort",
]
