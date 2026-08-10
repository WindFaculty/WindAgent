"""Studio repository adapters (Plan A — A3, studio.contract/v0.1).

Async SQLAlchemy adapters behind the A2 ``*RepositoryPort`` protocols plus the
event store and run persistence. Conventions:

- Dual-read compatibility: ``get`` reads the canonical Studio table first and
  falls back to the legacy V2 table (``video_production_projects`` /
  ``video_production_revisions``) so pre-migration databases stay readable.
  Legacy rows are mapped through the same deterministic backfill helpers the
  A3 migration uses, so both paths produce identical identities.
- Canonical writes are gated by the reversible ``STUDIO_CANONICAL_WRITES``
  flag (default on after migration validation; set to ``0`` to fail closed
  back to read-only without touching data).
- Optimistic concurrency for mutable aggregates (episode, revision) is
  enforced with a guarded UPDATE on ``optimistic_version``.
- Unique artifact hash, revision hash-per-episode, approval binding, and
  per-aggregate event sequence are enforced by migration indexes; adapters
  translate constraint violations into domain errors and keep idempotent
  saves idempotent.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.contracts.studio.errors import (
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.domain.studio.approval import (
    ApprovalPolicy,
    StudioApprovalDecision,
)
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.revision import (
    StudioLockState,
    StudioProductionRevision,
    StudioRevisionStatus,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.domain.video_production.ids import VideoProjectId
from windagent_core.domain.video_production.project import ProjectStatus, VideoProject
from windagent_core.events.studio import StudioEventEnvelope

from windagent_storage.orm.studio_models import (
    StudioApprovalDecisionORM,
    StudioApprovalPolicyORM,
    StudioArtifactORM,
    StudioEpisodeORM,
    StudioEventORM,
    StudioRevisionORM,
    StudioRunORM,
    StudioSeriesProjectORM,
)
from windagent_storage.studio.backfill import (
    map_legacy_status,
    normalize_legacy_hash,
    revision_metadata,
    series_metadata,
    synthetic_episode_id,
    lock_state_for,
)
from windagent_storage.video_production.video_production_models import (
    ProductionProjectORM,
    ProductionRevisionORM,
)


def canonical_writes_enabled() -> bool:
    """Reversible canonical-write flag (STUDIO_CANONICAL_WRITES, default on)."""
    return os.environ.get("STUDIO_CANONICAL_WRITES", "1") not in {"0", "false", "False", ""}


def _require_canonical_writes(operation: str) -> None:
    if not canonical_writes_enabled():
        raise StudioValidationError(
            f"Canonical Studio writes are disabled (STUDIO_CANONICAL_WRITES=0); {operation} rejected.",
            details={"operation": operation},
        )


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _loads(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return fallback


def _episode_to_orm(ep: Episode) -> Dict[str, Any]:
    return {
        "episode_id": str(ep.episode_id),
        "series_id": str(ep.series_id),
        "title": ep.title,
        "episode_number": ep.episode_number,
        "state": ep.state.value,
        "current_revision_id": str(ep.current_revision_id) if ep.current_revision_id else None,
        "active_run_id": str(ep.active_run_id) if ep.active_run_id else None,
        "awaiting_checkpoint": ep.awaiting_checkpoint,
        "created_at": _naive(ep.created_at),
        "updated_at": _naive(ep.updated_at),
        "optimistic_version": ep.optimistic_version,
        "metadata_json": _dumps(ep.metadata),
    }


def _episode_from_orm(row: StudioEpisodeORM) -> Episode:
    return Episode.model_validate(
        {
            "episode_id": EpisodeId(row.episode_id),
            "series_id": SeriesProjectId(row.series_id),
            "title": row.title,
            "episode_number": row.episode_number,
            "state": row.state,
            "current_revision_id": row.current_revision_id,
            "active_run_id": row.active_run_id,
            "awaiting_checkpoint": row.awaiting_checkpoint,
            "created_at": _aware(row.created_at),
            "updated_at": _aware(row.updated_at),
            "optimistic_version": row.optimistic_version,
            "metadata": _loads(row.metadata_json, {}),
        }
    )


def _revision_to_orm(rev: StudioProductionRevision) -> Dict[str, Any]:
    return {
        "revision_id": str(rev.revision_id),
        "series_id": str(rev.series_id),
        "episode_id": str(rev.episode_id),
        "parent_revision_id": str(rev.parent_revision_id) if rev.parent_revision_id else None,
        "creator": rev.creator,
        "actor": rev.actor,
        "created_at": _naive(rev.created_at),
        "content_hash": rev.content_hash,
        "state": rev.state.value,
        "status": rev.status.value,
        "lock_state": rev.lock_state.value,
        "invalidation_intent": rev.invalidation_intent.value if rev.invalidation_intent else None,
        "summary": rev.summary,
        "metadata_json": _dumps(rev.metadata),
        "optimistic_version": rev.optimistic_version,
    }


def _revision_from_orm(row: StudioRevisionORM) -> StudioProductionRevision:
    return StudioProductionRevision.model_validate(
        {
            "revision_id": ProductionRevisionId(row.revision_id),
            "series_id": SeriesProjectId(row.series_id),
            "episode_id": EpisodeId(row.episode_id),
            "parent_revision_id": row.parent_revision_id,
            "creator": row.creator,
            "actor": row.actor,
            "created_at": _aware(row.created_at),
            "content_hash": row.content_hash,
            "state": row.state,
            "status": row.status,
            "lock_state": row.lock_state,
            "invalidation_intent": row.invalidation_intent,
            "summary": row.summary,
            "metadata": _loads(row.metadata_json, {}),
            "optimistic_version": row.optimistic_version,
        }
    )


def _artifact_to_orm(art: StoryArtifactEnvelope) -> Dict[str, Any]:
    return {
        "artifact_id": str(art.artifact_id),
        "artifact_type": art.artifact_type.value,
        "schema_version": art.schema_version,
        "series_id": str(art.series_id),
        "episode_id": str(art.episode_id),
        "revision_id": str(art.revision_id) if art.revision_id else None,
        "content_hash": art.content_hash,
        "input_artifact_refs_json": _dumps([str(a) for a in art.input_artifact_refs]),
        "prompt_id": art.prompt_id,
        "prompt_version": art.prompt_version,
        "prompt_hash": art.prompt_hash,
        "model_route_id": art.model_route_id,
        "provider_id": art.provider_id,
        "model_id": art.model_id,
        "created_at": _naive(art.created_at),
        "created_by": art.created_by,
        "content_json": _dumps(art.content),
    }


def _artifact_from_orm(row: StudioArtifactORM) -> StoryArtifactEnvelope:
    return StoryArtifactEnvelope.model_validate(
        {
            "artifact_id": ArtifactId(row.artifact_id),
            "artifact_type": row.artifact_type,
            "schema_version": row.schema_version,
            "series_id": SeriesProjectId(row.series_id),
            "episode_id": EpisodeId(row.episode_id),
            "revision_id": row.revision_id,
            "content_hash": row.content_hash,
            "input_artifact_refs": _loads(row.input_artifact_refs_json, []),
            "prompt_id": row.prompt_id,
            "prompt_version": row.prompt_version,
            "prompt_hash": row.prompt_hash,
            "model_route_id": row.model_route_id,
            "provider_id": row.provider_id,
            "model_id": row.model_id,
            "created_at": _aware(row.created_at),
            "created_by": row.created_by,
            "content": _loads(row.content_json, {}),
        }
    )


class SqlSeriesProjectRepository:
    """Canonical SeriesProject repository with legacy dual-read fallback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, series_id: SeriesProjectId) -> Optional[SeriesProject]:
        stmt = select(StudioSeriesProjectORM).where(StudioSeriesProjectORM.series_id == str(series_id))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return SeriesProject.model_validate(
                {
                    "series_id": SeriesProjectId(row.series_id),
                    "title": row.title,
                    "description": row.description or "",
                    "episode_ids": [EpisodeId(e) for e in _loads(row.episode_ids_json, [])],
                    "created_at": _aware(row.created_at),
                    "updated_at": _aware(row.updated_at),
                    "metadata": _loads(row.metadata_json, {}),
                }
            )
        # Dual-read: legacy V2 project row before/without migration.
        legacy = (
            await self.session.execute(
                select(ProductionProjectORM).where(ProductionProjectORM.id == str(series_id))
            )
        ).scalar_one_or_none()
        if legacy is None:
            return None
        status = ProjectStatus.DRAFT
        try:
            status = ProjectStatus(legacy.status or "DRAFT")
        except ValueError:
            pass
        video = VideoProject(
            project_id=VideoProjectId(legacy.id),
            title=legacy.name or "Untitled Production",
            status=status,
            created_at=_aware(legacy.created_at),
            updated_at=_aware(legacy.updated_at),
        )
        return to_series_project_legacy(video, legacy.status, legacy.active_revision_id)

    async def save(self, project: SeriesProject) -> SeriesProject:
        _require_canonical_writes("SeriesProject.save")
        existing = (
            await self.session.execute(
                select(StudioSeriesProjectORM).where(
                    StudioSeriesProjectORM.series_id == str(project.series_id)
                )
            )
        ).scalar_one_or_none()
        values = {
            "title": project.title,
            "description": project.description or "",
            "episode_ids_json": _dumps([str(e) for e in project.episode_ids]),
            "created_at": _naive(project.created_at),
            "updated_at": _naive(project.updated_at),
            "metadata_json": _dumps(project.metadata),
        }
        if existing is None:
            self.session.add(
                StudioSeriesProjectORM(series_id=str(project.series_id), **values)
            )
        else:
            await self.session.execute(
                update(StudioSeriesProjectORM)
                .where(StudioSeriesProjectORM.series_id == str(project.series_id))
                .values(**values)
            )
        return project

    async def list(self, cursor: Optional[str] = None, limit: int = 100) -> List[SeriesProject]:
        stmt = select(StudioSeriesProjectORM).order_by(StudioSeriesProjectORM.series_id).limit(limit)
        if cursor:
            stmt = stmt.where(StudioSeriesProjectORM.series_id > cursor)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            SeriesProject.model_validate(
                {
                    "series_id": SeriesProjectId(r.series_id),
                    "title": r.title,
                    "description": r.description or "",
                    "episode_ids": [EpisodeId(e) for e in _loads(r.episode_ids_json, [])],
                    "created_at": _aware(r.created_at),
                    "updated_at": _aware(r.updated_at),
                    "metadata": _loads(r.metadata_json, {}),
                }
            )
            for r in rows
        ]


def to_series_project_legacy(
    video: VideoProject, legacy_status: Optional[str], legacy_active_revision_id: Optional[str]
) -> SeriesProject:
    """Map a legacy project row through the same deterministic metadata as the backfill."""
    from windagent_core.domain.studio.compat import to_series_project

    return to_series_project(
        video,
        metadata=series_metadata(
            legacy_status=legacy_status or video.status.value,
            legacy_active_revision_id=legacy_active_revision_id or "",
        ),
    )


class SqlEpisodeRepository:
    """Canonical Episode repository with optimistic concurrency."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, episode_id: EpisodeId) -> Optional[Episode]:
        stmt = select(StudioEpisodeORM).where(StudioEpisodeORM.episode_id == str(episode_id))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _episode_from_orm(row) if row is not None else None

    async def save(self, episode: Episode) -> Episode:
        _require_canonical_writes("Episode.save")
        existing = (
            await self.session.execute(
                select(StudioEpisodeORM).where(StudioEpisodeORM.episode_id == str(episode.episode_id))
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(StudioEpisodeORM(**_episode_to_orm(episode)))
            return episode
        expected = episode.optimistic_version - 1
        result = await self.session.execute(
            update(StudioEpisodeORM)
            .where(StudioEpisodeORM.episode_id == str(episode.episode_id))
            .where(StudioEpisodeORM.optimistic_version == expected)
            .values(**_episode_to_orm(episode))
        )
        if result.rowcount == 0:
            raise StudioStaleRevisionError(
                "Episode changed since it was read; optimistic version mismatch.",
                details={
                    "episode_id": str(episode.episode_id),
                    "expected_version": expected,
                    "current_version": existing.optimistic_version,
                },
            )
        return episode

    async def list_by_series(self, series_id: SeriesProjectId) -> List[Episode]:
        stmt = (
            select(StudioEpisodeORM)
            .where(StudioEpisodeORM.series_id == str(series_id))
            .order_by(StudioEpisodeORM.episode_number)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_episode_from_orm(r) for r in rows]


class SqlStudioRevisionRepository:
    """Canonical immutable-revision repository with legacy dual-read fallback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, revision_id: ProductionRevisionId) -> Optional[StudioProductionRevision]:
        stmt = select(StudioRevisionORM).where(StudioRevisionORM.revision_id == str(revision_id))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return _revision_from_orm(row)
        legacy = (
            await self.session.execute(
                select(ProductionRevisionORM).where(ProductionRevisionORM.id == str(revision_id))
            )
        ).scalar_one_or_none()
        if legacy is None:
            return None
        return _revision_from_legacy(legacy)

    async def save(self, revision: StudioProductionRevision) -> StudioProductionRevision:
        _require_canonical_writes("ProductionRevision.save")
        existing = (
            await self.session.execute(
                select(StudioRevisionORM).where(StudioRevisionORM.revision_id == str(revision.revision_id))
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(StudioRevisionORM(**_revision_to_orm(revision)))
            return revision
        expected = revision.optimistic_version - 1
        result = await self.session.execute(
            update(StudioRevisionORM)
            .where(StudioRevisionORM.revision_id == str(revision.revision_id))
            .where(StudioRevisionORM.optimistic_version == expected)
            .values(**_revision_to_orm(revision))
        )
        if result.rowcount == 0:
            raise StudioStaleRevisionError(
                "Revision changed since it was read; optimistic version mismatch.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_version": expected,
                    "current_version": existing.optimistic_version,
                },
            )
        return revision

    async def latest_for_episode(self, episode_id: EpisodeId) -> Optional[StudioProductionRevision]:
        stmt = (
            select(StudioRevisionORM)
            .where(StudioRevisionORM.episode_id == str(episode_id))
            .order_by(StudioRevisionORM.created_at.desc(), StudioRevisionORM.revision_id.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _revision_from_orm(row) if row is not None else None


def _revision_from_legacy(row: ProductionRevisionORM) -> StudioProductionRevision:
    """Dual-read mapping of a legacy revision row (identical to A3 backfill semantics)."""
    hash_backfilled = not (row.content_hash and len(row.content_hash) == 64)
    content_hash = normalize_legacy_hash(
        str(row.content_hash or ""), row.id, row.sequence or 0, row.status or "DRAFT"
    )
    mapped = map_legacy_status(row.status or "DRAFT")
    return StudioProductionRevision(
        revision_id=ProductionRevisionId(row.id),
        series_id=SeriesProjectId(row.project_id),
        episode_id=EpisodeId(synthetic_episode_id(row.project_id)),
        parent_revision_id=ProductionRevisionId(row.parent_revision_id) if row.parent_revision_id else None,
        creator="legacy:migration",
        actor="legacy:migration",
        created_at=_aware(row.created_at),
        content_hash=content_hash,
        state=StudioRevisionStatus(mapped),
        status=StudioRevisionStatus(mapped),
        lock_state=StudioLockState(lock_state_for(row.status or "DRAFT", mapped)),
        metadata=revision_metadata(
            legacy_status=row.status or "DRAFT",
            legacy_sequence=row.sequence or 0,
            hash_backfilled=hash_backfilled,
        ),
    )


class SqlStoryArtifactRepository:
    """Canonical immutable artifact repository; content-addressed idempotent saves."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, artifact_id: ArtifactId) -> Optional[StoryArtifactEnvelope]:
        stmt = select(StudioArtifactORM).where(StudioArtifactORM.artifact_id == str(artifact_id))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _artifact_from_orm(row) if row is not None else None

    async def save(self, artifact: StoryArtifactEnvelope) -> StoryArtifactEnvelope:
        _require_canonical_writes("StoryArtifact.save")
        by_id = (
            await self.session.execute(
                select(StudioArtifactORM).where(StudioArtifactORM.artifact_id == str(artifact.artifact_id))
            )
        ).scalar_one_or_none()
        if by_id is not None:
            return _artifact_from_orm(by_id)
        by_hash = (
            await self.session.execute(
                select(StudioArtifactORM).where(StudioArtifactORM.content_hash == artifact.content_hash)
            )
        ).scalar_one_or_none()
        if by_hash is not None:
            raise StudioValidationError(
                "Artifact content hash already exists under a different artifact id.",
                details={"content_hash": artifact.content_hash, "existing_artifact_id": by_hash.artifact_id},
            )
        self.session.add(StudioArtifactORM(**_artifact_to_orm(artifact)))
        return artifact

    async def find_by_hash(self, content_hash: str) -> Optional[StoryArtifactEnvelope]:
        stmt = select(StudioArtifactORM).where(StudioArtifactORM.content_hash == content_hash)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _artifact_from_orm(row) if row is not None else None

    async def list_for_episode(self, episode_id: EpisodeId) -> List[StoryArtifactEnvelope]:
        stmt = (
            select(StudioArtifactORM)
            .where(StudioArtifactORM.episode_id == str(episode_id))
            .order_by(StudioArtifactORM.created_at)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_artifact_from_orm(r) for r in rows]


class SqlApprovalRepository:
    """Canonical approval policy/decision repository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_policy(
        self, policy_id: str, policy_version: Optional[str] = None
    ) -> Optional[ApprovalPolicy]:
        stmt = select(StudioApprovalPolicyORM).where(
            StudioApprovalPolicyORM.policy_id == policy_id
        )
        if policy_version:
            stmt = stmt.where(StudioApprovalPolicyORM.policy_version == policy_version)
        stmt = stmt.order_by(StudioApprovalPolicyORM.policy_version.desc()).limit(1)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ApprovalPolicy.model_validate(
            {
                "policy_id": row.policy_id,
                "policy_version": row.policy_version,
                "checkpoint_to_mode_map": _loads(row.checkpoint_to_mode_json, {}),
                "quality_thresholds": _loads(row.quality_thresholds_json, {}),
                "max_review_revision_iterations": row.max_review_revision_iterations,
                "required_approver_roles": set(_loads(row.required_approver_roles_json, ["OWNER"])),
                "effective_time": _aware(row.effective_time),
            }
        )

    async def save_policy(self, policy: ApprovalPolicy) -> ApprovalPolicy:
        _require_canonical_writes("ApprovalPolicy.save")
        values = {
            "checkpoint_to_mode_json": _dumps(
                {k.value: v.value for k, v in policy.checkpoint_to_mode_map.items()}
            ),
            "quality_thresholds_json": _dumps(
                {k.value: v for k, v in policy.quality_thresholds.items()}
            ),
            "max_review_revision_iterations": policy.max_review_revision_iterations,
            "required_approver_roles_json": _dumps(sorted(policy.required_approver_roles)),
            "effective_time": _naive(policy.effective_time),
        }
        existing = (
            await self.session.execute(
                select(StudioApprovalPolicyORM).where(
                    StudioApprovalPolicyORM.policy_id == policy.policy_id,
                    StudioApprovalPolicyORM.policy_version == policy.policy_version,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(
                StudioApprovalPolicyORM(
                    policy_id=policy.policy_id, policy_version=policy.policy_version, **values
                )
            )
        else:
            await self.session.execute(
                update(StudioApprovalPolicyORM)
                .where(
                    StudioApprovalPolicyORM.policy_id == policy.policy_id,
                    StudioApprovalPolicyORM.policy_version == policy.policy_version,
                )
                .values(**values)
            )
        return policy

    async def record_decision(self, decision: StudioApprovalDecision) -> StudioApprovalDecision:
        _require_canonical_writes("ApprovalDecision.record")
        # Deterministic approval_id (domain: appr_<revision>_<checkpoint>_<actor>) makes
        # replays idempotent without touching the transaction.
        existing = await self.get_decision(decision.approval_id)
        if existing is not None:
            return existing
        self.session.add(
            StudioApprovalDecisionORM(
                approval_id=decision.approval_id,
                aggregate_id=str(decision.aggregate_id),
                revision_id=str(decision.revision_id),
                artifact_hash=decision.artifact_hash,
                checkpoint=decision.checkpoint.value,
                actor=decision.actor,
                role=decision.role,
                decision=decision.decision.value,
                reason=decision.reason,
                timestamp=_naive(decision.timestamp),
            )
        )
        return decision

    async def get_decision(self, approval_id: str) -> Optional[StudioApprovalDecision]:
        stmt = select(StudioApprovalDecisionORM).where(
            StudioApprovalDecisionORM.approval_id == approval_id
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _decision_from_orm(row) if row is not None else None

    async def decisions_for_revision(
        self, revision_id: ProductionRevisionId
    ) -> List[StudioApprovalDecision]:
        stmt = (
            select(StudioApprovalDecisionORM)
            .where(StudioApprovalDecisionORM.revision_id == str(revision_id))
            .order_by(StudioApprovalDecisionORM.timestamp)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_decision_from_orm(r) for r in rows]


def _decision_from_orm(row: StudioApprovalDecisionORM) -> StudioApprovalDecision:
    return StudioApprovalDecision.model_validate(
        {
            "approval_id": row.approval_id,
            "aggregate_id": EpisodeId(row.aggregate_id),
            "revision_id": ProductionRevisionId(row.revision_id),
            "artifact_hash": row.artifact_hash,
            "checkpoint": row.checkpoint,
            "actor": row.actor,
            "role": row.role,
            "decision": row.decision,
            "reason": row.reason,
            "timestamp": _aware(row.timestamp),
        }
    )


class SqlStudioRunRepository:
    """Durable run persistence (consumed by A4 orchestration)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, run_id: StudioRunId, series_id: SeriesProjectId, episode_id: EpisodeId,
                   dag: Dict[str, Any], status: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        _require_canonical_writes("StudioRun.save")
        existing = (
            await self.session.execute(
                select(StudioRunORM).where(StudioRunORM.run_id == str(run_id))
            )
        ).scalar_one_or_none()
        now = _naive(datetime.now(timezone.utc))
        values = {
            "series_id": str(series_id),
            "episode_id": str(episode_id),
            "dag_json": _dumps(dag),
            "status": status,
            "updated_at": now,
            "metadata_json": _dumps(metadata or {}),
        }
        if existing is None:
            self.session.add(StudioRunORM(run_id=str(run_id), created_at=now, **values))
        else:
            await self.session.execute(
                update(StudioRunORM).where(StudioRunORM.run_id == str(run_id)).values(**values)
            )

    async def get(self, run_id: StudioRunId) -> Optional[Dict[str, Any]]:
        stmt = select(StudioRunORM).where(StudioRunORM.run_id == str(run_id))
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "run_id": row.run_id,
            "series_id": row.series_id,
            "episode_id": row.episode_id,
            "dag": _loads(row.dag_json, {}),
            "status": row.status,
            "created_at": _aware(row.created_at),
            "updated_at": _aware(row.updated_at),
            "metadata": _loads(row.metadata_json, {}),
        }


class SqlStudioEventRepository:
    """Event store with per-aggregate sequence allocation (unique per aggregate)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._session_max: Dict[str, int] = {}

    async def _db_max_sequence(self, aggregate_id: str) -> int:
        stmt = (
            select(func.max(StudioEventORM.sequence))
            .where(StudioEventORM.aggregate_id == aggregate_id)
        )
        value = (await self.session.execute(stmt)).scalar()
        return int(value or 0)

    async def append(self, event: StudioEventEnvelope) -> StudioEventEnvelope:
        """Insert the event with the next per-aggregate sequence; returns the assigned copy."""
        base = max(await self._db_max_sequence(event.aggregate_id), self._session_max.get(event.aggregate_id, 0))
        sequence = base + 1
        self._session_max[event.aggregate_id] = sequence
        assigned = event.model_copy(update={"sequence": sequence})
        self.session.add(
            StudioEventORM(
                event_id=assigned.event_id,
                event_type=assigned.event_type,
                schema_version=assigned.schema_version,
                aggregate_id=assigned.aggregate_id,
                aggregate_type=assigned.aggregate_type,
                sequence=assigned.sequence,
                occurred_at=_naive(assigned.occurred_at),
                correlation_id=assigned.correlation_id,
                causation_id=assigned.causation_id,
                studio_run_id=str(assigned.studio_run_id) if assigned.studio_run_id else None,
                revision_ref=assigned.revision_ref,
                artifact_refs_json=_dumps([str(a) for a in assigned.artifact_refs]),
                payload_json=_dumps(assigned.payload),
            )
        )
        return assigned

    async def events_after(
        self, run_id: StudioRunId, after_sequence: int = 0, limit: int = 100
    ) -> List[StudioEventEnvelope]:
        stmt = (
            select(StudioEventORM)
            .where(StudioEventORM.studio_run_id == str(run_id))
            .where(StudioEventORM.sequence > after_sequence)
            .order_by(StudioEventORM.sequence)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_event_from_orm(r) for r in rows]

    async def latest_sequence(self, run_id: StudioRunId) -> int:
        stmt = select(func.max(StudioEventORM.sequence)).where(
            StudioEventORM.studio_run_id == str(run_id)
        )
        value = (await self.session.execute(stmt)).scalar()
        return int(value or 0)


def _event_from_orm(row: StudioEventORM) -> StudioEventEnvelope:
    return StudioEventEnvelope.model_validate(
        {
            "event_id": row.event_id,
            "event_type": row.event_type,
            "schema_version": row.schema_version,
            "aggregate_id": row.aggregate_id,
            "aggregate_type": row.aggregate_type,
            "sequence": row.sequence,
            "occurred_at": _aware(row.occurred_at),
            "correlation_id": row.correlation_id,
            "causation_id": row.causation_id,
            "studio_run_id": StudioRunId(row.studio_run_id) if row.studio_run_id else None,
            "revision_ref": row.revision_ref,
            "artifact_refs": [ArtifactId(a) for a in _loads(row.artifact_refs_json, [])],
            "payload": _loads(row.payload_json, {}),
        }
    )


__all__ = [
    "canonical_writes_enabled",
    "SqlSeriesProjectRepository",
    "SqlEpisodeRepository",
    "SqlStudioRevisionRepository",
    "SqlStoryArtifactRepository",
    "SqlApprovalRepository",
    "SqlStudioRunRepository",
    "SqlStudioEventRepository",
]
