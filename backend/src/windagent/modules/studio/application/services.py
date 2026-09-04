"""Application service orchestrating the Studio aggregates.

Every command runs inside one ``TransactionScope`` (platform UoW + outbox),
so the domain write and the durable event are atomically committed.  The
service validates aggregates through the pure domain layer and translates
rows to/from domain models at the boundary.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.time import Clock
from windagent.platform.observability import Telemetry

from ..domain.characters.character import Character
from ..domain.episodes.episode import Episode
from ..domain.episodes.revision import (
    InvalidationIntent,
    LockState,
    ProductionRevision,
    RevisionService,
    RevisionStatus,
)
from ..domain.errors import StudioNotFoundError, StudioValidationError
from ..domain.lifecycle import EpisodeState
from ..domain.projects.project import Project
from ..domain.series.series import SeriesProject
from ..domain.story.artifact import ArtifactType
from ..domain.storyboard.storyboard import Storyboard, StoryboardPanel
from .events import StudioEventFactory
from .models import (
    ArtifactRow,
    CharacterRow,
    EpisodeRow,
    ProjectRow,
    RevisionRow,
    SeriesRow,
    StoryboardRow,
    WorldLocationRow,
    WorldPropRow,
)
from .ports import TransactionScope


def _new_id(prefix: str = "") -> str:
    raw = str(uuid.uuid4())
    return f"{prefix}{raw}" if prefix else raw


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _load(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class StudioService:
    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        clock: Clock,
        event_factory: StudioEventFactory,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._clock = clock
        self._events = event_factory
        self._telemetry = telemetry

    # ------------------------------------------------------------------ #
    # Row -> View helpers (kept here to avoid leaking rows to handlers)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _project_view(row: ProjectRow) -> Any:
        from .models import ProjectView

        return ProjectView(
            project_id=row.project_id,
            title=row.title,
            description=row.description,
            owner_id=row.owner_id,
            series_ids=tuple(_load(row.series_ids_json, [])),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _series_view(row: SeriesRow) -> Any:
        from .models import SeriesView

        return SeriesView(
            series_id=row.series_id,
            project_id=row.project_id,
            title=row.title,
            description=row.description,
            episode_ids=tuple(_load(row.episode_ids_json, [])),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _episode_view(row: EpisodeRow) -> Any:
        from .models import EpisodeView

        return EpisodeView(
            episode_id=row.episode_id,
            series_id=row.series_id,
            project_id=row.project_id,
            title=row.title,
            episode_number=row.episode_number,
            logline=row.logline,
            state=row.state,
            current_revision_id=row.current_revision_id,
            active_run_id=row.active_run_id,
            awaiting_checkpoint=row.awaiting_checkpoint,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _revision_view(row: RevisionRow) -> Any:
        from .models import RevisionView

        return RevisionView(
            revision_id=row.revision_id,
            series_id=row.series_id,
            episode_id=row.episode_id,
            parent_revision_id=row.parent_revision_id,
            creator=row.creator,
            actor=row.actor,
            created_at=_as_utc(row.created_at),
            content_hash=row.content_hash,
            status=row.status,
            lock_state=row.lock_state,
            invalidation_intent=row.invalidation_intent,
            summary=row.summary,
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _artifact_view(row: ArtifactRow) -> Any:
        from .models import ArtifactView

        return ArtifactView(
            artifact_id=row.artifact_id,
            artifact_type=row.artifact_type,
            schema_version=row.schema_version,
            series_id=row.series_id,
            episode_id=row.episode_id,
            revision_id=row.revision_id,
            content_hash=row.content_hash,
            input_artifact_refs=tuple(_load(row.input_refs_json, [])),
            created_at=_as_utc(row.created_at),
            created_by=row.created_by,
            content=_load(row.content_json, {}),
            extra=_load(row.extra_json, {}),
        )

    @staticmethod
    def _character_view(row: CharacterRow) -> Any:
        from .models import CharacterView

        return CharacterView(
            character_id=row.character_id,
            series_id=row.series_id,
            name=row.name,
            display_name=row.display_name,
            role=row.role,
            archetype=row.archetype,
            description=row.description,
            traits=tuple(_load(row.traits_json, [])),
            backstory=row.backstory,
            portrait_artifact_id=row.portrait_artifact_id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _storyboard_view(row: StoryboardRow) -> Any:
        from .models import StoryboardView

        return StoryboardView(
            storyboard_id=row.storyboard_id,
            episode_id=row.episode_id,
            series_id=row.series_id,
            title=row.title,
            panels=tuple(_load(row.panels_json, [])),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    # ------------------------------------------------------------------ #
    # Projects
    # ------------------------------------------------------------------ #

    async def create_project(self, *, title: str, description: str = "", owner_id: str = "system", metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise StudioValidationError("Project title cannot be blank.")
        project_id = _new_id()
        now = datetime.now(UTC)
        row = ProjectRow(
            project_id=project_id,
            title=normalized,
            description=description,
            owner_id=owner_id,
            series_ids_json=_dump([]),
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            ok = await store.insert_project(row)
            if not ok:
                raise StudioValidationError("Project id collision — retry.", context={"project_id": project_id})
            await scope.record_event(self._events.project_created(project_id, normalized))
            await scope.commit()
            inserted = await store.get_project(project_id)
            assert inserted is not None
            return self._project_view(inserted)

    async def update_project(self, *, project_id: str, title: str | None, description: str | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_project(project_id)
            if existing is None:
                raise StudioNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            domain = Project(
                project_id=existing.project_id,
                title=existing.title,
                description=existing.description,
                owner_id=existing.owner_id,
                series_ids=tuple(_load(existing.series_ids_json, [])),
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            changes: dict[str, Any] = {}
            if title is not None:
                renamed = domain.rename(title, expected_version=expected_version)
                if renamed is not domain:
                    changes["title"] = renamed.title
                    domain = renamed
            if description is not None and description != existing.description:
                changes["description"] = description
            if metadata_patch:
                merged = dict(_load(existing.metadata_json, {}))
                merged.update(metadata_patch)
                if merged != _load(existing.metadata_json, {}):
                    changes["metadata_json"] = _dump(merged)
                    changes["optimistic_version"] = domain.optimistic_version + (0 if "title" in changes else 1)
            if title is not None and "title" in changes:
                changes["optimistic_version"] = domain.optimistic_version
                changes["metadata_json"] = _dump(_load(existing.metadata_json, {}))
            # If only description changed without version bump, bump explicitly
            if description is not None and "description" in changes and "optimistic_version" not in changes:
                changes["optimistic_version"] = existing.optimistic_version + 1
            if not changes:
                return self._project_view(existing)
            # stale check via underlying store compare-and-swap
            updated = await store.update_project(
                project_id,
                title=changes.get("title"),
                description=changes.get("description"),
                series_ids_json=None,
                optimistic_version=changes.get("optimistic_version"),
                expected_version=expected_version,
                metadata_json=changes.get("metadata_json"),
            )
            if updated is None:
                # Either not found after stale or optimistic mismatch — surface as staleness
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Project optimistic version mismatch.", context={"project_id": project_id})
            await scope.commit()
            return self._project_view(updated)

    async def get_project(self, project_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_project(project_id)
            if row is None:
                raise StudioNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            return self._project_view(row)

    async def list_projects(self) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_projects()
            return tuple(self._project_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Series
    # ------------------------------------------------------------------ #

    async def create_series(self, *, title: str, description: str = "", project_id: str | None = None, metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise StudioValidationError("Series title cannot be blank.")
        series_id = _new_id()
        now = datetime.now(UTC)
        row = SeriesRow(
            series_id=series_id,
            project_id=project_id,
            title=normalized,
            description=description,
            episode_ids_json=_dump([]),
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            if project_id is not None:
                proj = await store.get_project(project_id)
                if proj is None:
                    raise StudioNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            ok = await store.insert_series(row)
            if not ok:
                raise StudioValidationError("Series id collision — retry.")
            # attach to project atomically
            if project_id is not None:
                existing = await store.get_project(project_id)
                assert existing is not None
                series_ids = _load(existing.series_ids_json, [])
                series_ids.append(series_id)
                await store.update_project(
                    project_id,
                    title=None,
                    description=None,
                    series_ids_json=_dump(series_ids),
                    optimistic_version=existing.optimistic_version + 1,
                    expected_version=existing.optimistic_version,
                    metadata_json=None,
                )
            await scope.record_event(self._events.series_created(series_id, normalized, project_id))
            await scope.commit()
            inserted = await store.get_series(series_id)
            assert inserted is not None
            return self._series_view(inserted)

    async def update_series(self, *, series_id: str, title: str | None, description: str | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_series(series_id)
            if existing is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            domain = SeriesProject(
                series_id=existing.series_id,
                project_id=existing.project_id,
                title=existing.title,
                description=existing.description,
                episode_ids=tuple(_load(existing.episode_ids_json, [])),
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            updated_domain = domain.edit(
                title=title, description=description, metadata_patch=metadata_patch, expected_version=expected_version
            )
            if updated_domain is domain:
                return self._series_view(existing)
            updated = await store.update_series(
                series_id,
                title=updated_domain.title if updated_domain.title != existing.title else None,
                description=updated_domain.description if updated_domain.description != existing.description else None,
                episode_ids_json=None,
                optimistic_version=updated_domain.optimistic_version,
                expected_version=expected_version,
                metadata_json=_dump(updated_domain.metadata) if updated_domain.metadata != _load(existing.metadata_json, {}) else None,
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Series optimistic version mismatch.", context={"series_id": series_id})
            await scope.commit()
            return self._series_view(updated)

    async def get_series(self, series_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_series(series_id)
            if row is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            return self._series_view(row)

    async def list_series(self, project_id: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_series(project_id)
            return tuple(self._series_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Episodes
    # ------------------------------------------------------------------ #

    async def create_episode(self, *, series_id: str, title: str, episode_number: int = 1, logline: str = "", project_id: str | None = None, metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise StudioValidationError("Episode title cannot be blank.")
        if episode_number < 1:
            raise StudioValidationError("episode_number must be >= 1.")
        episode_id = _new_id()
        now = datetime.now(UTC)
        row = EpisodeRow(
            episode_id=episode_id,
            series_id=series_id,
            project_id=project_id,
            title=normalized,
            episode_number=episode_number,
            logline=logline,
            state=EpisodeState.DRAFT.value,
            current_revision_id=None,
            active_run_id=None,
            awaiting_checkpoint=None,
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            series = await store.get_series(series_id)
            if series is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            ok = await store.insert_episode(row)
            if not ok:
                raise StudioValidationError("Episode id collision — retry.")
            # attach to series
            episode_ids = _load(series.episode_ids_json, [])
            episode_ids.append(episode_id)
            await store.update_series(
                series_id,
                title=None,
                description=None,
                episode_ids_json=_dump(episode_ids),
                optimistic_version=series.optimistic_version + 1,
                expected_version=series.optimistic_version,
                metadata_json=None,
            )
            await scope.record_event(self._events.episode_created(episode_id, series_id, normalized))
            await scope.commit()
            inserted = await store.get_episode(episode_id)
            assert inserted is not None
            return self._episode_view(inserted)

    async def update_episode(self, *, episode_id: str, title: str | None, logline: str | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_episode(episode_id)
            if existing is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            domain = Episode(
                episode_id=existing.episode_id,
                series_id=existing.series_id,
                project_id=existing.project_id,
                title=existing.title,
                episode_number=existing.episode_number,
                logline=existing.logline,
                state=EpisodeState(existing.state),
                current_revision_id=existing.current_revision_id,
                active_run_id=existing.active_run_id,
                awaiting_checkpoint=existing.awaiting_checkpoint,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            updated_domain = domain.edit(
                title=title, logline=logline, metadata_patch=metadata_patch, expected_version=expected_version
            )
            if updated_domain is domain:
                return self._episode_view(existing)
            updated = await store.update_episode(
                episode_id,
                title=updated_domain.title if updated_domain.title != existing.title else None,
                logline=updated_domain.logline if updated_domain.logline != existing.logline else None,
                optimistic_version=updated_domain.optimistic_version,
                expected_version=expected_version,
                metadata_json=_dump(updated_domain.metadata) if updated_domain.metadata != _load(existing.metadata_json, {}) else None,
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Episode optimistic version mismatch.", context={"episode_id": episode_id})
            await scope.commit()
            return self._episode_view(updated)

    async def transition_episode(self, *, episode_id: str, target_state: str, expected_version: int | None) -> Any:
        try:
            target = EpisodeState(target_state)
        except ValueError as exc:
            raise StudioValidationError(f"Unknown episode state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_episode(episode_id)
            if existing is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            domain = Episode(
                episode_id=existing.episode_id,
                series_id=existing.series_id,
                project_id=existing.project_id,
                title=existing.title,
                episode_number=existing.episode_number,
                logline=existing.logline,
                state=EpisodeState(existing.state),
                current_revision_id=existing.current_revision_id,
                active_run_id=existing.active_run_id,
                awaiting_checkpoint=existing.awaiting_checkpoint,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            prev_state = domain.state.value
            updated_domain = domain.transition_to(target, expected_version=expected_version)
            updated = await store.update_episode(
                episode_id,
                state=updated_domain.state.value,
                awaiting_checkpoint=updated_domain.awaiting_checkpoint,
                optimistic_version=updated_domain.optimistic_version,
                expected_version=expected_version,
                metadata_json=None,
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Episode optimistic version mismatch.", context={"episode_id": episode_id})
            await scope.record_event(self._events.episode_transitioned(episode_id, prev_state, target.value))
            await scope.commit()
            return self._episode_view(updated)

    async def get_episode(self, episode_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_episode(episode_id)
            if row is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            return self._episode_view(row)

    async def list_episodes(self, series_id: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_episodes(series_id)
            return tuple(self._episode_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Revisions
    # ------------------------------------------------------------------ #

    async def create_revision(self, *, series_id: str, episode_id: str, content_hash: str, creator: str = "system", actor: str | None = None, parent_revision_id: str | None = None, summary: str = "", metadata: dict[str, Any] | None = None) -> Any:
        if len(content_hash) != 64:
            raise StudioValidationError("content_hash must be a 64-char SHA-256 hex digest.")
        revision_id = _new_id()
        now = datetime.now(UTC)
        row = RevisionRow(
            revision_id=revision_id,
            series_id=series_id,
            episode_id=episode_id,
            parent_revision_id=parent_revision_id,
            creator=creator,
            actor=actor or creator,
            created_at=now,
            content_hash=content_hash,
            status=RevisionStatus.DRAFT.value,
            lock_state=LockState.UNLOCKED.value,
            invalidation_intent=None,
            summary=summary,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            episode = await store.get_episode(episode_id)
            if episode is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            if parent_revision_id is not None:
                parent = await store.get_revision(parent_revision_id)
                if parent is None:
                    raise StudioNotFoundError(f"Parent revision {parent_revision_id!r} not found.", context={"revision_id": parent_revision_id})
            ok = await store.insert_revision(row)
            if not ok:
                raise StudioValidationError("Revision id collision — retry.")
            # attach to episode if no current revision
            if episode.current_revision_id is None:
                await store.update_episode(
                    episode_id,
                    current_revision_id=revision_id,
                    optimistic_version=episode.optimistic_version + 1,
                    expected_version=episode.optimistic_version,
                )
            await scope.record_event(self._events.revision_created(revision_id, episode_id))
            await scope.commit()
            inserted = await store.get_revision(revision_id)
            assert inserted is not None
            return self._revision_view(inserted)

    async def derive_revision(self, *, episode_id: str, series_id: str, parent_revision_id: str, new_content_hash: str, actor: str = "system", invalidation_intent: str | None = None, summary: str = "", expected_version: int | None = None) -> Any:
        if len(new_content_hash) != 64:
            raise StudioValidationError("new_content_hash must be a 64-char SHA-256 hex digest.")
        async with self._scope_factory() as scope:
            store = scope.store()
            parent_row = await store.get_revision(parent_revision_id)
            if parent_row is None:
                raise StudioNotFoundError(f"Parent revision {parent_revision_id!r} not found.", context={"revision_id": parent_revision_id})
            parent_domain = ProductionRevision(
                revision_id=parent_row.revision_id,
                series_id=parent_row.series_id,
                episode_id=parent_row.episode_id,
                parent_revision_id=parent_row.parent_revision_id,
                creator=parent_row.creator,
                actor=parent_row.actor,
                created_at=_as_utc(parent_row.created_at) or datetime.now(UTC),
                content_hash=parent_row.content_hash,
                status=RevisionStatus(parent_row.status),
                lock_state=LockState(parent_row.lock_state),
                invalidation_intent=InvalidationIntent(parent_row.invalidation_intent) if parent_row.invalidation_intent else None,
                summary=parent_row.summary,
                optimistic_version=parent_row.optimistic_version,
                metadata=_load(parent_row.metadata_json, {}),
            )
            intent_enum = InvalidationIntent(invalidation_intent) if invalidation_intent else None
            derived = RevisionService.derive_revision(
                parent=parent_domain,
                series_id=series_id,
                episode_id=episode_id,
                new_content_hash=new_content_hash,
                creator=actor,
                actor=actor,
                invalidation_intent=intent_enum,
                summary=summary,
                expected_parent_version=expected_version,
            )
            now = datetime.now(UTC)
            row = RevisionRow(
                revision_id=derived.revision_id,
                series_id=derived.series_id,
                episode_id=derived.episode_id,
                parent_revision_id=derived.parent_revision_id,
                creator=derived.creator,
                actor=derived.actor,
                created_at=now,
                content_hash=derived.content_hash,
                status=derived.status.value,
                lock_state=derived.lock_state.value,
                invalidation_intent=derived.invalidation_intent.value if derived.invalidation_intent else None,
                summary=derived.summary,
                optimistic_version=derived.optimistic_version,
                metadata_json=_dump(derived.metadata),
            )
            ok = await store.insert_revision(row)
            if not ok:
                raise StudioValidationError("Derived revision collision — retry.")
            # bump episode to point to derived
            episode = await store.get_episode(episode_id)
            if episode is not None:
                await store.update_episode(
                    episode_id,
                    current_revision_id=derived.revision_id,
                    optimistic_version=episode.optimistic_version + 1,
                    expected_version=episode.optimistic_version,
                )
            await scope.record_event(self._events.revision_created(derived.revision_id, episode_id))
            await scope.commit()
            inserted = await store.get_revision(derived.revision_id)
            assert inserted is not None
            return self._revision_view(inserted)

    async def lock_revision(self, *, revision_id: str, expected_content_hash: str | None = None, expected_version: int | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_revision(revision_id)
            if existing is None:
                raise StudioNotFoundError(f"Revision {revision_id!r} not found.", context={"revision_id": revision_id})
            domain = ProductionRevision(
                revision_id=existing.revision_id,
                series_id=existing.series_id,
                episode_id=existing.episode_id,
                parent_revision_id=existing.parent_revision_id,
                creator=existing.creator,
                actor=existing.actor,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                content_hash=existing.content_hash,
                status=RevisionStatus(existing.status),
                lock_state=LockState(existing.lock_state),
                invalidation_intent=InvalidationIntent(existing.invalidation_intent) if existing.invalidation_intent else None,
                summary=existing.summary,
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            locked = RevisionService.lock_revision(
                revision=domain, expected_content_hash=expected_content_hash, expected_version=expected_version
            )
            if locked is domain:
                return self._revision_view(existing)
            updated = await store.update_revision(
                revision_id,
                status=locked.status.value,
                lock_state=locked.lock_state.value,
                optimistic_version=locked.optimistic_version,
                expected_version=expected_version,
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Revision optimistic version mismatch.", context={"revision_id": revision_id})
            # also transition episode to LOCKED if not already
            ep_row = await store.get_episode(existing.episode_id)
            if ep_row is not None and ep_row.state != EpisodeState.LOCKED.value and ep_row.state != EpisodeState.READY_FOR_PRODUCTION.value:
                try:
                    domain_ep = Episode(
                        episode_id=ep_row.episode_id,
                        series_id=ep_row.series_id,
                        project_id=ep_row.project_id,
                        title=ep_row.title,
                        episode_number=ep_row.episode_number,
                        logline=ep_row.logline,
                        state=EpisodeState(ep_row.state),
                        current_revision_id=ep_row.current_revision_id,
                        active_run_id=ep_row.active_run_id,
                        awaiting_checkpoint=ep_row.awaiting_checkpoint,
                        created_at=_as_utc(ep_row.created_at) or datetime.now(UTC),
                        updated_at=_as_utc(ep_row.updated_at) or datetime.now(UTC),
                        optimistic_version=ep_row.optimistic_version,
                        metadata=_load(ep_row.metadata_json, {}),
                    )
                    bumped = domain_ep.start_lock_sequence(expected_version=ep_row.optimistic_version)
                    await store.update_episode(
                        ep_row.episode_id,
                        state=bumped.state.value,
                        optimistic_version=bumped.optimistic_version,
                        expected_version=ep_row.optimistic_version,
                    )
                except Exception:
                    pass
            await scope.record_event(self._events.revision_locked(revision_id, existing.episode_id))
            await scope.commit()
            refreshed = await store.get_revision(revision_id)
            assert refreshed is not None
            return self._revision_view(refreshed)

    async def get_revision(self, revision_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_revision(revision_id)
            if row is None:
                raise StudioNotFoundError(f"Revision {revision_id!r} not found.", context={"revision_id": revision_id})
            return self._revision_view(row)

    async def list_revisions(self, episode_id: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_revisions(episode_id)
            return tuple(self._revision_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Artifacts
    # ------------------------------------------------------------------ #

    async def create_artifact(self, *, artifact_type: str, series_id: str, episode_id: str, content: Any, revision_id: str | None = None, input_artifact_refs: tuple[str, ...] = (), created_by: str = "system", extra: dict[str, Any] | None = None) -> Any:
        try:
            artifact_enum = ArtifactType(artifact_type)
        except ValueError as exc:
            raise StudioValidationError(f"Unknown artifact type {artifact_type!r}.") from exc
        # hash
        from ..domain.story.artifact import canonical_content_hash

        content_hash = canonical_content_hash(content=content)
        artifact_id = _new_id()
        now = datetime.now(UTC)
        row = ArtifactRow(
            artifact_id=artifact_id,
            artifact_type=artifact_enum.value,
            schema_version="studio.artifact/v1alpha1",
            series_id=series_id,
            episode_id=episode_id,
            revision_id=revision_id,
            content_hash=content_hash,
            input_refs_json=_dump(list(input_artifact_refs)),
            created_at=now,
            created_by=created_by,
            content_json=_dump(content),
            extra_json=_dump(extra or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            # validate episode/series exist
            episode = await store.get_episode(episode_id)
            if episode is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            ok = await store.insert_artifact(row)
            if not ok:
                raise StudioValidationError("Artifact id collision — retry.")
            await scope.record_event(self._events.artifact_created(artifact_id, episode_id, artifact_enum.value))
            await scope.commit()
            inserted = await store.get_artifact(artifact_id)
            assert inserted is not None
            return self._artifact_view(inserted)

    async def get_artifact(self, artifact_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_artifact(artifact_id)
            if row is None:
                raise StudioNotFoundError(f"Artifact {artifact_id!r} not found.", context={"artifact_id": artifact_id})
            return self._artifact_view(row)

    async def list_artifacts(self, episode_id: str | None = None, artifact_type: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_artifacts(episode_id, artifact_type)
            return tuple(self._artifact_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Characters
    # ------------------------------------------------------------------ #

    async def create_character(self, *, series_id: str, name: str, display_name: str = "", role: str = "supporting", archetype: str = "", description: str = "", traits: tuple[str, ...] = (), backstory: str = "", metadata: dict[str, Any] | None = None) -> Any:
        normalized = name.strip()
        if not normalized:
            raise StudioValidationError("Character name cannot be blank.")
        character_id = _new_id()
        now = datetime.now(UTC)
        row = CharacterRow(
            character_id=character_id,
            series_id=series_id,
            name=normalized,
            display_name=display_name,
            role=role,
            archetype=archetype,
            description=description,
            traits_json=_dump(list(traits)),
            backstory=backstory,
            portrait_artifact_id=None,
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            series = await store.get_series(series_id)
            if series is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            ok = await store.insert_character(row)
            if not ok:
                raise StudioValidationError("Character id collision — retry.")
            await scope.commit()
            inserted = await store.get_character(character_id)
            assert inserted is not None
            return self._character_view(inserted)

    async def update_character(self, *, character_id: str, display_name: str | None, description: str | None, traits: tuple[str, ...] | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_character(character_id)
            if existing is None:
                raise StudioNotFoundError(f"Character {character_id!r} not found.", context={"character_id": character_id})
            domain = Character(
                character_id=existing.character_id,
                series_id=existing.series_id,
                name=existing.name,
                display_name=existing.display_name,
                role=existing.role,
                archetype=existing.archetype,
                description=existing.description,
                traits=tuple(_load(existing.traits_json, [])),
                backstory=existing.backstory,
                portrait_artifact_id=existing.portrait_artifact_id,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            # version guard
            if expected_version is not None and existing.optimistic_version != expected_version:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Character optimistic version mismatch.", context={"character_id": character_id})
            updated_domain = domain.edit(
                display_name=display_name, description=description, traits=traits, metadata_patch=metadata_patch
            )
            if updated_domain is domain:
                return self._character_view(existing)
            values: dict[str, Any] = {}
            if updated_domain.display_name != existing.display_name:
                values["display_name"] = updated_domain.display_name
            if updated_domain.description != existing.description:
                values["description"] = updated_domain.description
            if tuple(_load(existing.traits_json, [])) != updated_domain.traits:
                values["traits_json"] = _dump(list(updated_domain.traits))
            if updated_domain.metadata != _load(existing.metadata_json, {}):
                values["metadata_json"] = _dump(updated_domain.metadata)
            values["optimistic_version"] = updated_domain.optimistic_version
            values["updated_at"] = datetime.now(UTC)
            # we use generic update via store
            updated = await store.update_character(character_id, values=values)
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Character optimistic version mismatch.", context={"character_id": character_id})
            await scope.commit()
            return self._character_view(updated)

    async def get_character(self, character_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_character(character_id)
            if row is None:
                raise StudioNotFoundError(f"Character {character_id!r} not found.", context={"character_id": character_id})
            return self._character_view(row)

    async def list_characters(self, series_id: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_characters(series_id)
            return tuple(self._character_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # World
    # ------------------------------------------------------------------ #

    async def upsert_location(self, *, series_id: str, location_id: str, name: str, description: str = "", geography: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:  # type: ignore[return]
        normalized = name.strip()
        if not normalized:
            raise StudioValidationError("Location name cannot be blank.")
        now = datetime.now(UTC)
        row = WorldLocationRow(
            location_id=location_id,
            series_id=series_id,
            name=normalized,
            description=description,
            geography=geography,
            metadata_json=_dump(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            series = await store.get_series(series_id)
            if series is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            saved = await store.upsert_location(row)
            await scope.commit()
            return {
                "location_id": saved.location_id,
                "series_id": saved.series_id,
                "name": saved.name,
                "description": saved.description,
                "geography": saved.geography,
                "metadata": _load(saved.metadata_json, {}),
            }

    async def list_locations(self, series_id: str) -> tuple[dict[str, Any], ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_locations(series_id)
            return tuple(
                {
                    "location_id": row.location_id,
                    "series_id": row.series_id,
                    "name": row.name,
                    "description": row.description,
                    "geography": row.geography,
                    "metadata": _load(row.metadata_json, {}),
                }
                for row in rows
            )

    async def upsert_prop(self, *, series_id: str, prop_id: str, name: str, description: str = "", significance: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:  # type: ignore[return]
        normalized = name.strip()
        if not normalized:
            raise StudioValidationError("Prop name cannot be blank.")
        now = datetime.now(UTC)
        row = WorldPropRow(
            prop_id=prop_id,
            series_id=series_id,
            name=normalized,
            description=description,
            significance=significance,
            metadata_json=_dump(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            series = await store.get_series(series_id)
            if series is None:
                raise StudioNotFoundError(f"Series {series_id!r} not found.", context={"series_id": series_id})
            saved = await store.upsert_prop(row)
            await scope.commit()
            return {
                "prop_id": saved.prop_id,
                "series_id": saved.series_id,
                "name": saved.name,
                "description": saved.description,
                "significance": saved.significance,
                "metadata": _load(saved.metadata_json, {}),
            }

    async def list_props(self, series_id: str) -> tuple[dict[str, Any], ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_props(series_id)
            return tuple(
                {
                    "prop_id": row.prop_id,
                    "series_id": row.series_id,
                    "name": row.name,
                    "description": row.description,
                    "significance": row.significance,
                    "metadata": _load(row.metadata_json, {}),
                }
                for row in rows
            )

    # ------------------------------------------------------------------ #
    # Storyboard
    # ------------------------------------------------------------------ #

    async def create_storyboard(self, *, episode_id: str, series_id: str, title: str, panels: tuple[dict[str, Any], ...] = (), metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise StudioValidationError("Storyboard title cannot be blank.")
        storyboard_id = _new_id()
        now = datetime.now(UTC)
        row = StoryboardRow(
            storyboard_id=storyboard_id,
            episode_id=episode_id,
            series_id=series_id,
            title=normalized,
            panels_json=_dump(list(panels)),
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            episode = await store.get_episode(episode_id)
            if episode is None:
                raise StudioNotFoundError(f"Episode {episode_id!r} not found.", context={"episode_id": episode_id})
            ok = await store.insert_storyboard(row)
            if not ok:
                raise StudioValidationError("Storyboard id collision — retry.")
            await scope.commit()
            inserted = await store.get_storyboard(storyboard_id)
            assert inserted is not None
            return self._storyboard_view(inserted)

    async def update_storyboard(self, *, storyboard_id: str, panels: tuple[dict[str, Any], ...] | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_storyboard(storyboard_id)
            if existing is None:
                raise StudioNotFoundError(f"Storyboard {storyboard_id!r} not found.", context={"storyboard_id": storyboard_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Storyboard optimistic version mismatch.", context={"storyboard_id": storyboard_id})
            panels_json = None
            metadata_json = None
            if panels is not None:
                panels_json = _dump(list(panels))
            if metadata_patch:
                merged = _load(existing.metadata_json, {})
                merged.update(metadata_patch)
                metadata_json = _dump(merged)
            new_version = existing.optimistic_version + 1 if panels_json is not None or metadata_json is not None else None
            if new_version is None:
                return self._storyboard_view(existing)
            updated = await store.update_storyboard(
                storyboard_id, panels_json=panels_json, optimistic_version=new_version, expected_version=expected_version, metadata_json=metadata_json
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Storyboard optimistic version mismatch.", context={"storyboard_id": storyboard_id})
            await scope.commit()
            return self._storyboard_view(updated)

    async def reorder_storyboard(self, *, storyboard_id: str, panel_ids: tuple[str, ...], expected_version: int | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_storyboard(storyboard_id)
            if existing is None:
                raise StudioNotFoundError(f"Storyboard {storyboard_id!r} not found.", context={"storyboard_id": storyboard_id})
            storyboard = Storyboard(
                storyboard_id=existing.storyboard_id,
                episode_id=existing.episode_id,
                series_id=existing.series_id,
                title=existing.title,
                panels=tuple(
                    StoryboardPanel(
                        panel_id=panel["panel_id"],
                        scene_index=int(panel.get("scene_index", 0)),
                        description=str(panel.get("description", "")),
                        camera=str(panel.get("camera", "")),
                        dialogue_refs=tuple(panel.get("dialogue_refs", [])),
                        duration_seconds=float(panel.get("duration_seconds", 0.0)),
                    )
                    for panel in _load(existing.panels_json, [])
                ),
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            if expected_version is not None and storyboard.optimistic_version != expected_version:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Storyboard optimistic version mismatch.", context={"storyboard_id": storyboard_id})
            reordered = storyboard.reorder(panel_ids)
            panels_payload = [panel.model_dump(mode="json") for panel in reordered.panels]
            updated = await store.update_storyboard(
                storyboard_id,
                panels_json=_dump(panels_payload),
                optimistic_version=reordered.optimistic_version,
                expected_version=expected_version,
                metadata_json=None,
            )
            if updated is None:
                from ..domain.errors import StudioStaleRevisionError

                raise StudioStaleRevisionError("Storyboard optimistic version mismatch.", context={"storyboard_id": storyboard_id})
            await scope.commit()
            return self._storyboard_view(updated)

    async def get_storyboard(self, storyboard_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_storyboard(storyboard_id)
            if row is None:
                raise StudioNotFoundError(f"Storyboard {storyboard_id!r} not found.", context={"storyboard_id": storyboard_id})
            return self._storyboard_view(row)

    async def list_storyboards(self, episode_id: str | None = None) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_storyboards(episode_id)
            return tuple(self._storyboard_view(row) for row in rows)