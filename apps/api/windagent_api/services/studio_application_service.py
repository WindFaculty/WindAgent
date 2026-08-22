"""
Plan C1 application adapter for the canonical Studio surface (/api/v3/studio).

This service is the ONLY app-facing Studio entry point the V3 routers may call.
It binds to Plan A ports (``StudioRunOrchestratorPort`` and the read/capability
ports from ``windagent_core.contracts.studio.ports``) and maps commands/results
to the frozen payloads. Routers never orchestrate or persist.

Fail-closed composition: until Plan A handoff (A3/A4) wires real port
implementations into the container, the corresponding service methods raise
``StudioCapabilityUnavailableError``. There is no fake or fallback production
path; tests inject fake port implementations through FastAPI dependency
overrides.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    UpdateEpisodeCommand,
    UpdateSeriesCommand,
)
from windagent_core.contracts.studio.errors import (
    StudioCapabilityUnavailableError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.contracts.studio.ports import (
    ApprovalRepositoryPort,
    EpisodeRepositoryPort,
    ProductionRevisionRepositoryPort,
    RuntimeCapabilityPort,
    SeriesProjectRepositoryPort,
    StoryArtifactRepositoryPort,
    StudioEventQueryPort,
    StudioRunOrchestratorPort,
    StudioRunQueryPort,
)
from windagent_core.errors.exceptions import IdentityValidationError


class StudioApplicationService:
    """Maps frozen V3 requests to Plan A Studio ports and canonical payloads.

    Every mutating method requires an idempotency key and forwards the
    frozen command shape; expected revision/version/hash enforcement happens
    inside the Plan A authority (or its test double), not here.
    """

    def __init__(
        self,
        *,
        orchestrator: Optional[StudioRunOrchestratorPort] = None,
        run_query: Optional[StudioRunQueryPort] = None,
        event_query: Optional[StudioEventQueryPort] = None,
        capability: Optional[RuntimeCapabilityPort] = None,
        series_repo: Optional[SeriesProjectRepositoryPort] = None,
        episodes_repo: Optional[EpisodeRepositoryPort] = None,
        revisions_repo: Optional[ProductionRevisionRepositoryPort] = None,
        artifacts_repo: Optional[StoryArtifactRepositoryPort] = None,
        approvals_repo: Optional[ApprovalRepositoryPort] = None,
        preflight: Optional[Any] = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.run_query = run_query
        self.event_query = event_query
        self.capability = capability
        self.series_repo = series_repo
        self.episodes_repo = episodes_repo
        self.revisions_repo = revisions_repo
        self.artifacts_repo = artifacts_repo
        self.approvals_repo = approvals_repo
        #: Story Start preflight (P0.4.1); composed with real provider/routing
        #: authorities. Optional so tests can drive mutations without it.
        self.preflight = preflight

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _require(port: Any, name: str, detail: str) -> Any:
        if port is None:
            raise StudioCapabilityUnavailableError(
                f"Studio {name} is not composed yet.",
                details={"missing": name, "reason": detail},
            )
        return port

    def parse_id(self, id_cls: Any, value: str, label: str) -> Any:
        try:
            return id_cls(value)
        except (IdentityValidationError, TypeError, ValueError) as ex:
            raise StudioValidationError(
                f"Invalid {label}: {value!r}.",
                details={"field": label, "value": value},
                cause=ex,
            ) from ex

    @staticmethod
    def _assert_episode_match(path_episode_id: str, command_episode_id: EpisodeId) -> None:
        if str(command_episode_id) != path_episode_id:
            raise StudioValidationError(
                "episode_id in body does not match the URL path.",
                details={"path": path_episode_id, "body": str(command_episode_id)},
            )

    @staticmethod
    def _jsonable(model: Any) -> Dict[str, Any]:
        return model.model_dump(mode="json")

    # -- mutations (delegated to the Plan A orchestrator authority) -------

    async def create_series(
        self,
        *,
        title: str,
        description: str,
        metadata: Dict[str, Any],
        idempotency_key: str,
    ) -> CreateSeriesResult:
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.create_series(
            CreateSeriesCommand(
                title=title,
                description=description,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
        )

    async def create_episode(
        self,
        *,
        path_series_id: str,
        series_id: SeriesProjectId,
        title: str,
        episode_number: int,
        metadata: Dict[str, Any],
        idempotency_key: str,
    ) -> CreateEpisodeResult:
        if str(series_id) != path_series_id:
            raise StudioValidationError(
                "series_id in body does not match the URL path.",
                details={"path": path_series_id, "body": str(series_id)},
            )
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.create_episode(
            CreateEpisodeCommand(
                series_id=series_id,
                title=title,
                episode_number=episode_number,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
        )

    async def start_or_resume_run(self, *, episode_id: EpisodeId, idempotency_key: str) -> StartRunResult:
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.start_or_resume_run(
            StartRunCommand(episode_id=episode_id, idempotency_key=idempotency_key)
        )

    async def update_series(
        self,
        *,
        series_id: SeriesProjectId,
        title: Optional[str],
        description: Optional[str],
        metadata_patch: Dict[str, Any],
        idempotency_key: str,
    ) -> Any:
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.update_series(
            UpdateSeriesCommand(
                series_id=series_id,
                title=title,
                description=description,
                metadata_patch=metadata_patch,
                idempotency_key=idempotency_key,
            )
        )

    async def update_episode(
        self,
        *,
        path_episode_id: str,
        episode_id: EpisodeId,
        title: Optional[str],
        metadata_patch: Dict[str, Any],
        expected_optimistic_version: Optional[int],
        idempotency_key: str,
    ) -> Any:
        self._assert_episode_match(path_episode_id, episode_id)
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.update_episode(
            UpdateEpisodeCommand(
                episode_id=episode_id,
                title=title,
                metadata_patch=metadata_patch,
                expected_optimistic_version=expected_optimistic_version,
                idempotency_key=idempotency_key,
            )
        )

    async def preflight_start(self, *, episode_id: EpisodeId) -> Dict[str, Any]:
        """P0.4.1 — server-authoritative pre-start checks (truthful report)."""
        if self.preflight is None:
            raise StudioCapabilityUnavailableError(
                "Story start preflight is not composed.",
                details={"missing": "preflight"},
            )
        return await self.preflight.run(episode_id)

    async def select_idea(
        self,
        *,
        path_episode_id: str,
        episode_id: EpisodeId,
        revision_id: ProductionRevisionId,
        candidate_id: str,
        expected_content_hash: str,
        expected_optimistic_version: Optional[int],
        idempotency_key: str,
    ) -> SelectIdeaResult:
        self._assert_episode_match(path_episode_id, episode_id)
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.select_idea(
            SelectIdeaCommand(
                episode_id=episode_id,
                revision_id=revision_id,
                candidate_id=candidate_id,
                expected_content_hash=expected_content_hash,
                expected_optimistic_version=expected_optimistic_version,
                idempotency_key=idempotency_key,
            )
        )

    async def record_approval(
        self,
        *,
        path_episode_id: str,
        episode_id: EpisodeId,
        revision_id: ProductionRevisionId,
        checkpoint: str,
        artifact_hash: str,
        actor: str,
        decision: str,
        reason: str,
        expected_optimistic_version: Optional[int],
        idempotency_key: str,
    ) -> RecordApprovalResult:
        self._assert_episode_match(path_episode_id, episode_id)
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.record_approval(
            RecordApprovalCommand(
                episode_id=episode_id,
                revision_id=revision_id,
                checkpoint=checkpoint,
                artifact_hash=artifact_hash,
                actor=actor,
                decision=decision,
                reason=reason,
                expected_optimistic_version=expected_optimistic_version,
                idempotency_key=idempotency_key,
            )
        )

    async def derive_revision(
        self,
        *,
        path_episode_id: str,
        episode_id: EpisodeId,
        series_id: SeriesProjectId,
        parent_revision_id: ProductionRevisionId,
        new_content_hash: str,
        actor: str,
        invalidation_intent: Optional[str],
        summary: str,
        expected_optimistic_version: Optional[int],
        idempotency_key: str,
    ) -> DeriveRevisionResult:
        self._assert_episode_match(path_episode_id, episode_id)
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.derive_revision(
            DeriveRevisionCommand(
                episode_id=episode_id,
                series_id=series_id,
                parent_revision_id=parent_revision_id,
                new_content_hash=new_content_hash,
                actor=actor,
                invalidation_intent=invalidation_intent,
                summary=summary,
                expected_optimistic_version=expected_optimistic_version,
                idempotency_key=idempotency_key,
            )
        )

    async def lock_screenplay(
        self,
        *,
        path_episode_id: str,
        episode_id: EpisodeId,
        revision_id: ProductionRevisionId,
        expected_content_hash: str,
        expected_optimistic_version: Optional[int],
        idempotency_key: str,
    ) -> LockScreenplayResult:
        self._assert_episode_match(path_episode_id, episode_id)
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.lock_screenplay(
            LockScreenplayCommand(
                episode_id=episode_id,
                revision_id=revision_id,
                expected_content_hash=expected_content_hash,
                expected_optimistic_version=expected_optimistic_version,
                idempotency_key=idempotency_key,
            )
        )

    async def cancel_run(self, *, run_id: StudioRunId, actor: str, reason: str) -> Any:
        orchestrator = self._require(
            self.orchestrator, "orchestrator", "Plan A has not wired the Studio authority (A4)"
        )
        return await orchestrator.cancel_run(run_id, actor, reason)

    # -- read views ---------------------------------------------------------

    async def list_series(self, *, cursor: Optional[str], limit: int) -> Dict[str, Any]:
        repo = self._require(self.series_repo, "series repository", "Plan A persistence (A3) is not wired")
        items = await repo.list(cursor=cursor, limit=limit)
        return {
            "items": [self._series_view(s) for s in items],
            "next_cursor": str(items[-1].series_id) if items else None,
        }

    async def get_series(self, *, series_id: SeriesProjectId) -> Optional[Dict[str, Any]]:
        repo = self._require(self.series_repo, "series repository", "Plan A persistence (A3) is not wired")
        series = await repo.get(series_id)
        return self._series_view(series) if series else None

    @staticmethod
    def _series_view(series: Any) -> Dict[str, Any]:
        return {
            "id": str(series.series_id),
            "title": series.title,
            "description": series.description,
            "episode_ids": [str(e) for e in series.episode_ids],
            "episode_count": len(series.episode_ids),
            "created_at": series.created_at.isoformat(),
            "updated_at": series.updated_at.isoformat(),
            "metadata": series.metadata,
            "series_url": f"/api/v3/studio/series/{series.series_id}",
        }

    async def list_episodes(self, *, series_id: SeriesProjectId) -> List[Dict[str, Any]]:
        repo = self._require(self.episodes_repo, "episodes repository", "Plan A persistence (A3) is not wired")
        episodes = await repo.list_by_series(series_id)
        return [self._episode_view(e) for e in episodes]

    async def get_episode(self, *, episode_id: EpisodeId) -> Optional[Dict[str, Any]]:
        repo = self._require(self.episodes_repo, "episodes repository", "Plan A persistence (A3) is not wired")
        episode = await repo.get(episode_id)
        if episode is None:
            return None
        return await self._episode_view_full(episode)

    def _episode_view(self, episode: Any) -> Dict[str, Any]:
        return {
            "id": str(episode.episode_id),
            "series_id": str(episode.series_id),
            "title": episode.title,
            "episode_number": episode.episode_number,
            "state": episode.state.value,
            "version": episode.optimistic_version,
            "optimistic_version": episode.optimistic_version,
            "current_revision_id": (
                str(episode.current_revision_id) if episode.current_revision_id else None
            ),
            "active_run_id": str(episode.active_run_id) if episode.active_run_id else None,
            "episode_url": f"/api/v3/studio/episodes/{episode.episode_id}",
            "run_url": (
                f"/api/v3/studio/runs/{episode.active_run_id}" if episode.active_run_id else None
            ),
        }

    async def _episode_view_full(self, episode: Any) -> Dict[str, Any]:
        view = {
            **self._episode_view(episode),
            "awaiting_checkpoint": episode.awaiting_checkpoint,
            "created_at": episode.created_at.isoformat(),
            "updated_at": episode.updated_at.isoformat(),
            "metadata": episode.metadata,
        }
        if self.revisions_repo is not None and episode.current_revision_id is not None:
            revision = await self.revisions_repo.get(episode.current_revision_id)
            view["current_revision"] = self._revision_view(revision) if revision else None
        if self.approvals_repo is not None and episode.current_revision_id is not None:
            decisions = await self.approvals_repo.decisions_for_revision(episode.current_revision_id)
            view["approvals"] = [self._jsonable(d) for d in decisions]
        else:
            view["approvals"] = None
        if self.artifacts_repo is not None:
            artifacts = await self.artifacts_repo.list_for_episode(episode.episode_id)
            view["artifact_summary"] = {
                "count": len(artifacts),
                "types": sorted({a.artifact_type.value for a in artifacts}),
            }
        else:
            view["artifact_summary"] = None
        return view

    @staticmethod
    def _revision_view(revision: Any) -> Dict[str, Any]:
        if hasattr(revision, "model_dump_json_compat"):
            return revision.model_dump_json_compat()
        return revision.model_dump(mode="json")

    async def get_run(self, *, run_id: StudioRunId) -> Optional[Dict[str, Any]]:
        query = self._require(self.run_query, "run query", "Plan A read model (A3/A4) is not wired")
        run = await query.get_run(run_id)
        if run is None:
            return None
        return {**run, "run_url": f"/api/v3/studio/runs/{run_id}"}

    async def get_run_events(
        self, *, run_id: StudioRunId, after_sequence: int, limit: int
    ) -> Dict[str, Any]:
        query = self._require(self.event_query, "event query", "Plan A read model (A3/A4) is not wired")
        events = await query.events_after(run_id, after_sequence=after_sequence, limit=limit)
        latest = await query.latest_sequence(run_id)
        return {
            "run_id": str(run_id),
            "after_sequence": after_sequence,
            "latest_sequence": latest,
            "events": [e.to_dict() for e in events],
        }

    async def list_artifacts(self, *, episode_id: EpisodeId) -> List[Dict[str, Any]]:
        repo = self._require(self.artifacts_repo, "artifacts repository", "Plan A persistence (A3) is not wired")
        artifacts = await repo.list_for_episode(episode_id)
        return [self._artifact_view(a) for a in artifacts]

    async def get_artifact(self, *, artifact_id: ArtifactId) -> Optional[Dict[str, Any]]:
        repo = self._require(self.artifacts_repo, "artifacts repository", "Plan A persistence (A3) is not wired")
        artifact = await repo.get(artifact_id)
        return self._artifact_view(artifact) if artifact else None

    @staticmethod
    def _artifact_view(artifact: Any) -> Dict[str, Any]:
        return {
            "artifact_id": str(artifact.artifact_id),
            "artifact_type": artifact.artifact_type.value,
            "schema_version": artifact.schema_version,
            "series_id": str(artifact.series_id),
            "episode_id": str(artifact.episode_id),
            "revision_id": str(artifact.revision_id) if artifact.revision_id else None,
            "content_hash": artifact.content_hash,
            "input_artifact_refs": [str(r) for r in artifact.input_artifact_refs],
            "prompt_id": artifact.prompt_id,
            "prompt_version": artifact.prompt_version,
            "prompt_hash": artifact.prompt_hash,
            "model_route_id": artifact.model_route_id,
            "provider_id": artifact.provider_id,
            "model_id": artifact.model_id,
            "canonical_model_id": artifact.canonical_model_id,
            "provider_model_id": artifact.provider_model_id,
            "endpoint_id": artifact.endpoint_id,
            "provider_binding_id": artifact.provider_binding_id,
            "provider_attempt_id": artifact.provider_attempt_id,
            "provider_request_id": artifact.provider_request_id,
            "output_schema_contract": artifact.output_schema_contract,
            "created_at": artifact.created_at.isoformat(),
            "created_by": artifact.created_by,
            "content": artifact.content,
            "artifact_url": f"/api/v3/studio/artifacts/{artifact.artifact_id}",
        }

    # -- capability ---------------------------------------------------------

    async def get_capabilities(self) -> Any:
        port = self._require(
            self.capability, "capability probe", "capability provider is not composed"
        )
        return await port.get_capabilities()


__all__ = ["StudioApplicationService"]
