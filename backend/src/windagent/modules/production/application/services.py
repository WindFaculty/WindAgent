"""Application service orchestrating the Production aggregates.

Every command runs inside one ``TransactionScope`` (platform UoW + outbox),
so the domain write and the durable event are atomically committed.
"""

# mypy: disable-error-code="return"

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.time import Clock
from windagent.platform.observability import Telemetry

from ..domain.assets.asset import AssetKind, LicenseState, MediaType
from ..domain.assets.lifecycle import AssetLifecycleState, AssetStateMachine
from ..domain.code_video.code_video import CodeVideoProject, CodeVideoStatus
from ..domain.errors import (
    ProductionNotFoundError,
    ProductionStaleRevisionError,
    ProductionValidationError,
)
from ..domain.rendering.rendering import RenderJob, RenderStatus
from ..domain.video.project import (
    InvalidationIntent,
    ProductionRevision,
    ProjectStatus,
    RevisionService,
    RevisionStatus,
    VideoProject,
)
from .events import ProductionEventFactory
from .models import (
    AssetRevisionRow,
    AudioTrackRow,
    CodeVideoProjectRow,
    EdlRow,
    MixPlanRow,
    ProductionAssetRow,
    ProductionProjectRow,
    ProductionRevisionRow,
    RenderJobRow,
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


class ProductionService:
    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        clock: Clock,
        event_factory: ProductionEventFactory,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._clock = clock
        self._events = event_factory
        self._telemetry = telemetry

    # ------------------------------------------------------------------ #
    # Row -> View helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _project_view(row: ProductionProjectRow) -> Any:
        from .models import ProductionProjectView

        return ProductionProjectView(
            project_id=row.project_id,
            title=row.title,
            description=row.description,
            owner_id=row.owner_id,
            status=row.status,
            current_revision_id=row.current_revision_id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _revision_view(row: ProductionRevisionRow) -> Any:
        from .models import ProductionRevisionView

        return ProductionRevisionView(
            revision_id=row.revision_id,
            project_id=row.project_id,
            parent_revision_id=row.parent_revision_id,
            creator=row.creator,
            actor=row.actor,
            created_at=_as_utc(row.created_at),
            content_hash=row.content_hash,
            status=row.status,
            locked=row.locked,
            invalidation_intent=row.invalidation_intent,
            summary=row.summary,
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _asset_view(row: ProductionAssetRow) -> Any:
        from .models import ProductionAssetView

        return ProductionAssetView(
            asset_id=row.asset_id,
            project_id=row.project_id,
            name=row.name,
            kind=row.kind,
            lifecycle_state=row.lifecycle_state,
            processing_state=row.processing_state,
            active_revision_id=row.active_revision_id,
            source_type=row.source_type,
            license_state=row.license_state,
            tags=tuple(_load(row.tags_json, [])),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _asset_revision_view(row: AssetRevisionRow) -> Any:
        from .models import AssetRevisionView

        return AssetRevisionView(
            revision_id=row.revision_id,
            asset_id=row.asset_id,
            supersedes_revision_id=row.supersedes_revision_id,
            content_hash=row.content_hash,
            media_type=row.media_type,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            normalized_format=row.normalized_format,
            preview_artifacts=_load(row.preview_json, {}),
            validation_report=_load(row.validation_json, {}),
            provenance=_load(row.provenance_json, {}),
            created_at=_as_utc(row.created_at),
        )

    @staticmethod
    def _audio_track_view(row: AudioTrackRow) -> Any:
        from .models import AudioTrackView

        return AudioTrackView(
            track_id=row.track_id,
            project_id=row.project_id,
            kind=row.kind,
            title=row.title,
            character_id=row.character_id,
            dialogue_text=row.dialogue_text,
            source_path=row.source_path,
            source_hash=row.source_hash,
            sample_rate=row.sample_rate,
            channels=row.channels,
            duration_seconds=row.duration_seconds,
            language=row.language,
            voice_profile_id=row.voice_profile_id,
            rights_state=row.rights_state,
            provenance=_load(row.provenance_json, {}),
            created_at=_as_utc(row.created_at),
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _mix_plan_view(row: MixPlanRow) -> Any:
        from .models import MixPlanView

        return MixPlanView(
            mix_plan_id=row.mix_plan_id,
            project_id=row.project_id,
            title=row.title,
            loudness_target_lufs=row.loudness_target_lufs,
            peak_ceiling_db=row.peak_ceiling_db,
            policy_version=row.policy_version,
            tracks=tuple(_load(row.tracks_json, [])),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _code_video_view(row: CodeVideoProjectRow) -> Any:
        from .models import CodeVideoProjectView

        return CodeVideoProjectView(
            project_id=row.project_id,
            title=row.title,
            description=row.description,
            status=row.status,
            repo_url=row.repo_url,
            branch=row.branch,
            tutorial_steps=tuple(_load(row.tutorial_steps_json, [])),
            current_checkpoint=row.current_checkpoint,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _render_view(row: RenderJobRow) -> Any:
        from .models import RenderJobView

        return RenderJobView(
            job_id=row.job_id,
            project_id=row.project_id,
            revision_id=row.revision_id,
            scene_id=row.scene_id,
            shot_id=row.shot_id,
            status=row.status,
            frame_start=row.frame_start,
            frame_end=row.frame_end,
            colorspace=row.colorspace,
            profile_id=row.profile_id,
            attempt=row.attempt,
            input_hash=row.input_hash,
            output_hash=row.output_hash,
            error=row.error,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _edl_view(row: EdlRow) -> Any:
        from .models import EdlView

        return EdlView(
            edl_id=row.edl_id,
            project_id=row.project_id,
            revision_id=row.revision_id,
            title=row.title,
            status=row.status,
            items=tuple(_load(row.items_json, [])),
            audio_mix_plan_id=row.audio_mix_plan_id,
            subtitle_track_id=row.subtitle_track_id,
            encoding_profile=_load(row.encoding_profile_json, {}),
            edl_hash=row.edl_hash,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            metadata=_load(row.metadata_json, {}),
        )

    # ------------------------------------------------------------------ #
    # Projects
    # ------------------------------------------------------------------ #

    async def create_project(self, *, title: str, description: str = "", owner_id: str = "system", metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise ProductionValidationError("Project title cannot be blank.")
        project_id = _new_id()
        now = datetime.now(UTC)
        row = ProductionProjectRow(
            project_id=project_id,
            title=normalized,
            description=description,
            owner_id=owner_id,
            status=ProjectStatus.DRAFT.value,
            current_revision_id=None,
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            ok = await store.insert_project(row)
            if not ok:
                raise ProductionValidationError("Project id collision — retry.", context={"project_id": project_id})
            await scope.record_event(self._events.project_created(project_id, normalized))
            await scope.commit()
            inserted = await store.get_project(project_id)
            assert inserted is not None
            return self._project_view(inserted)

    async def update_project(
        self, *, project_id: str, title: str | None, description: str | None, status: str | None, expected_version: int | None, metadata_patch: dict[str, Any] | None
    ) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_project(project_id)
            if existing is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            domain = VideoProject(
                project_id=existing.project_id,
                title=existing.title,
                description=existing.description,
                owner_id=existing.owner_id,
                status=ProjectStatus(existing.status),
                current_revision_id=existing.current_revision_id,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            changes: dict[str, Any] = {}
            current_version = existing.optimistic_version
            # title via domain rename (handles staleness)
            if title is not None:
                renamed = domain.rename(title, expected_version=expected_version)
                if renamed is not domain:
                    changes["title"] = renamed.title
                    domain = renamed
                    current_version = renamed.optimistic_version
            if description is not None and description != existing.description:
                changes["description"] = description
                if "optimistic_version" not in changes:
                    # bump if not already bumped by rename
                    if title is None or "title" not in changes:
                        current_version = existing.optimistic_version + 1
                        changes["optimistic_version"] = current_version
            if status is not None:
                try:
                    st = ProjectStatus(status)
                except ValueError as exc:
                    raise ProductionValidationError(f"Unknown project status {status!r}.") from exc
                if st.value != existing.status:
                    changes["status"] = st.value
                    if "optimistic_version" not in changes:
                        current_version = existing.optimistic_version + 1 if "optimistic_version" not in changes else current_version
                        changes["optimistic_version"] = current_version if "optimistic_version" not in changes else changes["optimistic_version"]
            if metadata_patch:
                merged = dict(_load(existing.metadata_json, {}))
                merged.update(metadata_patch)
                if merged != _load(existing.metadata_json, {}):
                    changes["metadata_json"] = _dump(merged)
                    if "optimistic_version" not in changes:
                        # if only metadata changed, bump
                        changes["optimistic_version"] = existing.optimistic_version + 1 if "title" not in changes else changes["optimistic_version"]
            if not changes:
                return self._project_view(existing)
            # ensure optimistic_version is set
            if "optimistic_version" not in changes:
                # derive from domain if title changed else bump
                if "title" in changes:
                    changes["optimistic_version"] = domain.optimistic_version
                else:
                    changes["optimistic_version"] = existing.optimistic_version + 1
            updated = await store.update_project(
                project_id,
                title=changes.get("title"),
                description=changes.get("description"),
                status=changes.get("status"),
                current_revision_id=None,
                optimistic_version=changes.get("optimistic_version"),
                expected_version=expected_version,
                metadata_json=changes.get("metadata_json"),
            )
            if updated is None:
                raise ProductionStaleRevisionError("Project optimistic version mismatch.", context={"project_id": project_id})
            await scope.record_event(self._events.project_updated(project_id))
            await scope.commit()
            return self._project_view(updated)

    async def get_project(self, project_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_project(project_id)
            if row is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            return self._project_view(row)

    async def list_projects(self) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_projects()
            return tuple(self._project_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Revisions
    # ------------------------------------------------------------------ #

    async def create_revision(
        self, *, project_id: str, content_hash: str, creator: str = "system", actor: str | None = None, parent_revision_id: str | None = None, summary: str = "", metadata: dict[str, Any] | None = None
    ) -> Any:
        if len(content_hash) != 64:
            raise ProductionValidationError("content_hash must be a 64-char SHA-256 hex digest.")
        revision_id = _new_id()
        now = datetime.now(UTC)
        row = ProductionRevisionRow(
            revision_id=revision_id,
            project_id=project_id,
            parent_revision_id=parent_revision_id,
            creator=creator,
            actor=actor or creator,
            created_at=now,
            content_hash=content_hash,
            status=RevisionStatus.DRAFT.value,
            locked=False,
            invalidation_intent=None,
            summary=summary,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            proj = await store.get_project(project_id)
            if proj is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            if parent_revision_id is not None:
                parent = await store.get_revision(parent_revision_id)
                if parent is None:
                    raise ProductionNotFoundError(f"Parent revision {parent_revision_id!r} not found.", context={"revision_id": parent_revision_id})
            ok = await store.insert_revision(row)
            if not ok:
                raise ProductionValidationError("Revision id collision — retry.")
            if proj.current_revision_id is None:
                await store.update_project(
                    project_id,
                    title=None,
                    description=None,
                    status=None,
                    current_revision_id=revision_id,
                    optimistic_version=proj.optimistic_version + 1,
                    expected_version=proj.optimistic_version,
                    metadata_json=None,
                )
            await scope.record_event(self._events.revision_created(revision_id, project_id))
            await scope.commit()
            inserted = await store.get_revision(revision_id)
            assert inserted is not None
            return self._revision_view(inserted)

    async def derive_revision(
        self, *, project_id: str, parent_revision_id: str, new_content_hash: str, actor: str = "system", invalidation_intent: str | None = None, summary: str = "", expected_version: int | None = None
    ) -> Any:
        if len(new_content_hash) != 64:
            raise ProductionValidationError("new_content_hash must be a 64-char SHA-256 hex digest.")
        async with self._scope_factory() as scope:
            store = scope.store()
            parent_row = await store.get_revision(parent_revision_id)
            if parent_row is None:
                raise ProductionNotFoundError(f"Parent revision {parent_revision_id!r} not found.", context={"revision_id": parent_revision_id})
            parent_domain = ProductionRevision(
                revision_id=parent_row.revision_id,
                project_id=parent_row.project_id,
                parent_revision_id=parent_row.parent_revision_id,
                creator=parent_row.creator,
                actor=parent_row.actor,
                created_at=_as_utc(parent_row.created_at) or datetime.now(UTC),
                content_hash=parent_row.content_hash,
                status=RevisionStatus(parent_row.status),
                locked=parent_row.locked,
                invalidation_intent=InvalidationIntent(parent_row.invalidation_intent) if parent_row.invalidation_intent else None,
                summary=parent_row.summary,
                optimistic_version=parent_row.optimistic_version,
                metadata=_load(parent_row.metadata_json, {}),
            )
            intent_enum = InvalidationIntent(invalidation_intent) if invalidation_intent else None
            derived = RevisionService.derive_revision(
                parent=parent_domain,
                project_id=project_id,
                new_content_hash=new_content_hash,
                created_by=actor,
                actor=actor,
                invalidation_intent=intent_enum,
                summary=summary,
                expected_parent_version=expected_version,
            )
            now = datetime.now(UTC)
            row = ProductionRevisionRow(
                revision_id=derived.revision_id,
                project_id=derived.project_id,
                parent_revision_id=derived.parent_revision_id,
                creator=derived.creator,
                actor=derived.actor,
                created_at=now,
                content_hash=derived.content_hash,
                status=derived.status.value,
                locked=derived.locked,
                invalidation_intent=derived.invalidation_intent.value if derived.invalidation_intent else None,
                summary=derived.summary,
                optimistic_version=derived.optimistic_version,
                metadata_json=_dump(derived.metadata),
            )
            ok = await store.insert_revision(row)
            if not ok:
                raise ProductionValidationError("Derived revision collision — retry.")
            proj = await store.get_project(project_id)
            if proj is not None:
                await store.update_project(
                    project_id,
                    title=None,
                    description=None,
                    status=None,
                    current_revision_id=derived.revision_id,
                    optimistic_version=proj.optimistic_version + 1,
                    expected_version=proj.optimistic_version,
                    metadata_json=None,
                )
            await scope.record_event(self._events.revision_created(derived.revision_id, project_id))
            await scope.commit()
            inserted = await store.get_revision(derived.revision_id)
            assert inserted is not None
            return self._revision_view(inserted)

    async def lock_revision(self, *, revision_id: str, expected_content_hash: str | None = None, expected_version: int | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_revision(revision_id)
            if existing is None:
                raise ProductionNotFoundError(f"Revision {revision_id!r} not found.", context={"revision_id": revision_id})
            domain = ProductionRevision(
                revision_id=existing.revision_id,
                project_id=existing.project_id,
                parent_revision_id=existing.parent_revision_id,
                creator=existing.creator,
                actor=existing.actor,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                content_hash=existing.content_hash,
                status=RevisionStatus(existing.status),
                locked=existing.locked,
                invalidation_intent=InvalidationIntent(existing.invalidation_intent) if existing.invalidation_intent else None,
                summary=existing.summary,
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            locked = RevisionService.lock_revision(revision=domain, expected_content_hash=expected_content_hash, expected_version=expected_version)
            if locked is domain:
                return self._revision_view(existing)
            updated = await store.update_revision(
                revision_id,
                status=locked.status.value,
                locked=locked.locked,
                optimistic_version=locked.optimistic_version,
                expected_version=expected_version,
            )
            if updated is None:
                raise ProductionStaleRevisionError("Revision optimistic version mismatch.", context={"revision_id": revision_id})
            await scope.record_event(self._events.revision_locked(revision_id, existing.project_id))
            await scope.commit()
            refreshed = await store.get_revision(revision_id)
            assert refreshed is not None
            return self._revision_view(refreshed)

    async def get_revision(self, revision_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_revision(revision_id)
            if row is None:
                raise ProductionNotFoundError(f"Revision {revision_id!r} not found.", context={"revision_id": revision_id})
            return self._revision_view(row)

    async def list_revisions(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_revisions(project_id)
            return tuple(self._revision_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Assets
    # ------------------------------------------------------------------ #

    async def create_asset(
        self, *, name: str, kind: str = "OTHER", project_id: str | None = None, description: str = "", source_type: str = "UPLOADED", license_state: str = "UNKNOWN", tags: tuple[str, ...] = (), metadata: dict[str, Any] | None = None
    ) -> Any:
        normalized = name.strip()
        if not normalized:
            raise ProductionValidationError("Asset name cannot be blank.")
        try:
            kind_enum = AssetKind(kind)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown asset kind {kind!r}.") from exc
        try:
            LicenseState(license_state)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown license state {license_state!r}.") from exc
        asset_id = _new_id()
        now = datetime.now(UTC)
        row = ProductionAssetRow(
            asset_id=asset_id,
            project_id=project_id,
            name=normalized,
            kind=kind_enum.value,
            lifecycle_state=AssetLifecycleState.DISCOVERED.value,
            processing_state="IDLE",
            active_revision_id=None,
            source_type=source_type,
            license_state=license_state,
            tags_json=_dump(list(tags)),
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
                    raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            ok = await store.insert_asset(row)
            if not ok:
                raise ProductionValidationError("Asset id collision — retry.")
            await scope.record_event(self._events.asset_created(asset_id, project_id))
            await scope.commit()
            inserted = await store.get_asset(asset_id)
            assert inserted is not None
            return self._asset_view(inserted)

    async def transition_asset(self, *, asset_id: str, target_state: str, expected_version: int | None = None, new_review_record: bool = False) -> Any:
        try:
            target = AssetLifecycleState(target_state)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown asset state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_asset(asset_id)
            if existing is None:
                raise ProductionNotFoundError(f"Asset {asset_id!r} not found.", context={"asset_id": asset_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise ProductionStaleRevisionError("Asset optimistic version mismatch.", context={"asset_id": asset_id})
            current = AssetLifecycleState(existing.lifecycle_state)
            # use domain state machine which enforces review requirement
            AssetStateMachine.require_transition(current, target, new_review_record=new_review_record)
            prev_state = existing.lifecycle_state
            updated = await store.update_asset(
                asset_id,
                values={
                    "lifecycle_state": target.value,
                    "optimistic_version": existing.optimistic_version + 1,
                    "updated_at": datetime.now(UTC),
                },
            )
            if updated is None:
                raise ProductionStaleRevisionError("Asset optimistic version mismatch.", context={"asset_id": asset_id})
            await scope.record_event(self._events.asset_transitioned(asset_id, prev_state, target.value))
            await scope.commit()
            return self._asset_view(updated)

    async def get_asset(self, asset_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_asset(asset_id)
            if row is None:
                raise ProductionNotFoundError(f"Asset {asset_id!r} not found.", context={"asset_id": asset_id})
            return self._asset_view(row)

    async def list_assets(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_assets(project_id)
            return tuple(self._asset_view(row) for row in rows)

    async def create_asset_revision(
        self, *, asset_id: str, content_hash: str, media_type: str = "IMAGE", mime_type: str = "image/png", size_bytes: int = 0, supersedes_revision_id: str | None = None, normalized_format: str | None = None, preview_artifacts: dict[str, Any] | None = None, validation_report: dict[str, Any] | None = None, provenance: dict[str, Any] | None = None
    ) -> Any:
        if len(content_hash) != 64:
            raise ProductionValidationError("content_hash must be a 64-char SHA-256 hex digest.")
        try:
            MediaType(media_type)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown media type {media_type!r}.") from exc
        revision_id = _new_id()
        now = datetime.now(UTC)
        row = AssetRevisionRow(
            revision_id=revision_id,
            asset_id=asset_id,
            supersedes_revision_id=supersedes_revision_id,
            content_hash=content_hash,
            media_type=media_type,
            mime_type=mime_type,
            size_bytes=size_bytes,
            normalized_format=normalized_format,
            preview_json=_dump(preview_artifacts or {}),
            validation_json=_dump(validation_report or {}),
            provenance_json=_dump(provenance or {}),
            created_at=now,
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            asset = await store.get_asset(asset_id)
            if asset is None:
                raise ProductionNotFoundError(f"Asset {asset_id!r} not found.", context={"asset_id": asset_id})
            ok = await store.insert_asset_revision(row)
            if not ok:
                raise ProductionValidationError("Asset revision collision — retry.")
            # bump asset to point to active revision
            await store.update_asset(
                asset_id,
                values={"active_revision_id": revision_id, "optimistic_version": asset.optimistic_version + 1, "updated_at": now},
            )
            await scope.record_event(self._events.asset_revision_created(revision_id, asset_id))
            await scope.commit()
            inserted = await store.get_asset_revision(revision_id)
            assert inserted is not None
            return self._asset_revision_view(inserted)

    async def get_asset_revision(self, revision_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_asset_revision(revision_id)
            if row is None:
                raise ProductionNotFoundError(f"Asset revision {revision_id!r} not found.", context={"revision_id": revision_id})
            return self._asset_revision_view(row)

    async def list_asset_revisions(self, asset_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_asset_revisions(asset_id)
            return tuple(self._asset_revision_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Audio
    # ------------------------------------------------------------------ #

    async def create_audio_track(
        self, *, project_id: str, title: str, kind: str = "DIALOGUE", character_id: str | None = None, dialogue_text: str = "", source_path: str = "", source_hash: str = "", sample_rate: int = 48000, channels: int = 1, duration_seconds: float = 0.0, language: str = "en", voice_profile_id: str | None = None, provenance: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None
    ) -> Any:
        normalized = title.strip()
        if not normalized:
            raise ProductionValidationError("Audio track title cannot be blank.")
        from ..domain.audio.audio import AudioTrackKind

        try:
            AudioTrackKind(kind)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown audio kind {kind!r}.") from exc
        if source_hash and len(source_hash) != 64:
            # allow empty or 64 hex, but if provided validate is hex length
            raise ProductionValidationError("source_hash must be 64-char SHA-256 or empty.")
        track_id = _new_id()
        now = datetime.now(UTC)
        row = AudioTrackRow(
            track_id=track_id,
            project_id=project_id,
            kind=kind,
            title=normalized,
            character_id=character_id,
            dialogue_text=dialogue_text,
            source_path=source_path,
            source_hash=source_hash,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration_seconds,
            language=language,
            voice_profile_id=voice_profile_id,
            rights_state="PENDING",
            provenance_json=_dump(provenance or {}),
            created_at=now,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            proj = await store.get_project(project_id)
            if proj is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            ok = await store.insert_audio_track(row)
            if not ok:
                raise ProductionValidationError("Audio track collision — retry.")
            await scope.record_event(self._events.audio_track_created(track_id, project_id))
            await scope.commit()
            inserted = await store.get_audio_track(track_id)
            assert inserted is not None
            return self._audio_track_view(inserted)

    async def get_audio_track(self, track_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_audio_track(track_id)
            if row is None:
                raise ProductionNotFoundError(f"Audio track {track_id!r} not found.", context={"track_id": track_id})
            return self._audio_track_view(row)

    async def list_audio_tracks(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_audio_tracks(project_id)
            return tuple(self._audio_track_view(row) for row in rows)

    async def create_mix_plan(
        self, *, project_id: str, title: str = "main", loudness_target_lufs: float = -16.0, peak_ceiling_db: float = -1.0, policy_version: str = "loudness-v1", tracks: tuple[dict[str, Any], ...] = (), metadata: dict[str, Any] | None = None
    ) -> Any:
        mix_plan_id = _new_id()
        now = datetime.now(UTC)
        row = MixPlanRow(
            mix_plan_id=mix_plan_id,
            project_id=project_id,
            title=title,
            loudness_target_lufs=loudness_target_lufs,
            peak_ceiling_db=peak_ceiling_db,
            policy_version=policy_version,
            tracks_json=_dump(list(tracks)),
            created_at=now,
            updated_at=now,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            proj = await store.get_project(project_id)
            if proj is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            ok = await store.insert_mix_plan(row)
            if not ok:
                raise ProductionValidationError("Mix plan collision — retry.")
            await scope.record_event(self._events.mix_plan_created(mix_plan_id, project_id))
            await scope.commit()
            inserted = await store.get_mix_plan(mix_plan_id)
            assert inserted is not None
            return self._mix_plan_view(inserted)

    async def get_mix_plan(self, mix_plan_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_mix_plan(mix_plan_id)
            if row is None:
                raise ProductionNotFoundError(f"Mix plan {mix_plan_id!r} not found.", context={"mix_plan_id": mix_plan_id})
            return self._mix_plan_view(row)

    async def list_mix_plans(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_mix_plans(project_id)
            return tuple(self._mix_plan_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Code Video
    # ------------------------------------------------------------------ #

    async def create_code_video_project(self, *, title: str, description: str = "", repo_url: str = "", branch: str = "main", metadata: dict[str, Any] | None = None) -> Any:
        normalized = title.strip()
        if not normalized:
            raise ProductionValidationError("Code video project title cannot be blank.")
        from ..domain.code_video.code_video import CODE_VIDEO_STEPS

        project_id = _new_id()
        now = datetime.now(UTC)
        row = CodeVideoProjectRow(
            project_id=project_id,
            title=normalized,
            description=description,
            status=CodeVideoStatus.DRAFT.value,
            repo_url=repo_url,
            branch=branch,
            tutorial_steps_json=_dump(list(CODE_VIDEO_STEPS)),
            current_checkpoint=None,
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            ok = await store.insert_code_video_project(row)
            if not ok:
                raise ProductionValidationError("Code video project collision — retry.")
            await scope.record_event(self._events.code_video_created(project_id, normalized))
            await scope.commit()
            inserted = await store.get_code_video_project(project_id)
            assert inserted is not None
            return self._code_video_view(inserted)

    async def transition_code_video_project(self, *, project_id: str, target_status: str, expected_version: int | None = None) -> Any:
        try:
            target = CodeVideoStatus(target_status)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown code video status {target_status!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_code_video_project(project_id)
            if existing is None:
                raise ProductionNotFoundError(f"Code video project {project_id!r} not found.", context={"project_id": project_id})
            domain = CodeVideoProject(
                project_id=existing.project_id,
                title=existing.title,
                description=existing.description,
                status=CodeVideoStatus(existing.status),
                repo_url=existing.repo_url,
                branch=existing.branch,
                tutorial_steps=tuple(_load(existing.tutorial_steps_json, [])),
                current_checkpoint=existing.current_checkpoint,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            prev_status = domain.status.value
            updated_domain = domain.transition_to(target, expected_version=expected_version)
            updated = await store.update_code_video_project(
                project_id,
                values={
                    "status": updated_domain.status.value,
                    "optimistic_version": updated_domain.optimistic_version,
                    "updated_at": datetime.now(UTC),
                },
            )
            if updated is None:
                raise ProductionStaleRevisionError("Code video version mismatch.", context={"project_id": project_id})
            await scope.record_event(self._events.code_video_transitioned(project_id, prev_status, target.value))
            await scope.commit()
            return self._code_video_view(updated)

    async def get_code_video_project(self, project_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_code_video_project(project_id)
            if row is None:
                raise ProductionNotFoundError(f"Code video project {project_id!r} not found.", context={"project_id": project_id})
            return self._code_video_view(row)

    async def list_code_video_projects(self) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_code_video_projects()
            return tuple(self._code_video_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Render jobs
    # ------------------------------------------------------------------ #

    async def create_render_job(
        self, *, project_id: str, scene_id: str = "", shot_id: str = "", revision_id: str | None = None, frame_start: int = 1, frame_end: int = 24, colorspace: str = "sRGB", profile_id: str = "main_1080p_h264", input_hash: str = "", metadata: dict[str, Any] | None = None
    ) -> Any:
        if not colorspace.strip():
            raise ProductionValidationError("colorspace is required.")
        if frame_end < frame_start:
            raise ProductionValidationError("frame_end must be >= frame_start.")
        job_id = _new_id()
        now = datetime.now(UTC)
        row = RenderJobRow(
            job_id=job_id,
            project_id=project_id,
            revision_id=revision_id,
            scene_id=scene_id,
            shot_id=shot_id,
            status=RenderStatus.QUEUED.value,
            frame_start=frame_start,
            frame_end=frame_end,
            colorspace=colorspace,
            profile_id=profile_id,
            attempt=1,
            input_hash=input_hash,
            output_hash="",
            error="",
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            proj = await store.get_project(project_id)
            if proj is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            ok = await store.insert_render_job(row)
            if not ok:
                raise ProductionValidationError("Render job collision — retry.")
            await scope.record_event(self._events.render_job_created(job_id, project_id))
            await scope.commit()
            inserted = await store.get_render_job(job_id)
            assert inserted is not None
            return self._render_view(inserted)

    async def transition_render_job(self, *, job_id: str, target_status: str, expected_version: int | None = None, output_hash: str | None = None, error: str | None = None) -> Any:
        try:
            target = RenderStatus(target_status)
        except ValueError as exc:
            raise ProductionValidationError(f"Unknown render status {target_status!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_render_job(job_id)
            if existing is None:
                raise ProductionNotFoundError(f"Render job {job_id!r} not found.", context={"job_id": job_id})
            domain = RenderJob(
                job_id=existing.job_id,
                project_id=existing.project_id,
                revision_id=existing.revision_id,
                scene_id=existing.scene_id,
                shot_id=existing.shot_id,
                status=RenderStatus(existing.status),
                frame_start=existing.frame_start,
                frame_end=existing.frame_end,
                colorspace=existing.colorspace,
                profile_id=existing.profile_id,
                attempt=existing.attempt,
                input_hash=existing.input_hash,
                output_hash=existing.output_hash,
                error=existing.error,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                updated_at=_as_utc(existing.updated_at) or datetime.now(UTC),
                optimistic_version=existing.optimistic_version,
                metadata=_load(existing.metadata_json, {}),
            )
            prev_status = domain.status.value
            updated_domain = domain.transition_to(target, expected_version=expected_version)
            values: dict[str, Any] = {"status": updated_domain.status.value, "optimistic_version": updated_domain.optimistic_version, "updated_at": datetime.now(UTC)}
            if output_hash is not None:
                values["output_hash"] = output_hash
            if error is not None:
                values["error"] = error
            updated = await store.update_render_job(job_id, values=values)
            if updated is None:
                raise ProductionStaleRevisionError("Render job version mismatch.", context={"job_id": job_id})
            await scope.record_event(self._events.render_job_transitioned(job_id, prev_status, target.value))
            await scope.commit()
            return self._render_view(updated)

    async def get_render_job(self, job_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_render_job(job_id)
            if row is None:
                raise ProductionNotFoundError(f"Render job {job_id!r} not found.", context={"job_id": job_id})
            return self._render_view(row)

    async def list_render_jobs(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_render_jobs(project_id)
            return tuple(self._render_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # EDL / Post-production
    # ------------------------------------------------------------------ #

    async def create_edl(
        self, *, project_id: str, revision_id: str, title: str = "main", items: tuple[dict[str, Any], ...] = (), audio_mix_plan_id: str = "", subtitle_track_id: str | None = None, encoding_profile: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None
    ) -> Any:
        if not items:
            raise ProductionValidationError("EDL requires at least one item.")
        for item in items:
            if not item.get("clip_hash"):
                raise ProductionValidationError("EDL item clip_hash cannot be blank.", context={"item": item})
        edl_id = _new_id()
        now = datetime.now(UTC)
        payload = {"edl_id": edl_id, "project_id": project_id, "revision_id": revision_id, "items": list(items), "encoding": encoding_profile or {}}
        edl_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        if not encoding_profile:
            from ..domain.postproduction.postproduction import EncodingProfile as EP

            ep = EP.main_1080p_h264()
            enc_dict = {
                "profile_id": ep.profile_id,
                "preset": ep.preset.value,
                "container": ep.container.value,
                "video_codec": ep.video_codec,
                "video_crf": ep.video_crf,
                "resolution_width": ep.resolution_width,
                "resolution_height": ep.resolution_height,
                "frame_rate": ep.frame_rate,
                "pixel_format": ep.pixel_format,
                "audio_codec": ep.audio_codec,
                "audio_sample_rate": ep.audio_sample_rate,
                "audio_channels": ep.audio_channels,
                "audio_bitrate_kbps": ep.audio_bitrate_kbps,
            }
            enc_json = _dump(enc_dict)
        else:
            enc_json = _dump(encoding_profile)
        row = EdlRow(
            edl_id=edl_id,
            project_id=project_id,
            revision_id=revision_id,
            title=title,
            status="DRAFT",
            items_json=_dump(list(items)),
            audio_mix_plan_id=audio_mix_plan_id,
            subtitle_track_id=subtitle_track_id,
            encoding_profile_json=enc_json,
            edl_hash=edl_hash,
            created_at=now,
            updated_at=now,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            proj = await store.get_project(project_id)
            if proj is None:
                raise ProductionNotFoundError(f"Project {project_id!r} not found.", context={"project_id": project_id})
            rev = await store.get_revision(revision_id)
            if rev is None:
                raise ProductionNotFoundError(f"Revision {revision_id!r} not found.", context={"revision_id": revision_id})
            ok = await store.insert_edl(row)
            if not ok:
                raise ProductionValidationError("EDL collision — retry.")
            await scope.record_event(self._events.edl_created(edl_id, project_id))
            await scope.commit()
            inserted = await store.get_edl(edl_id)
            assert inserted is not None
            return self._edl_view(inserted)

    async def update_edl(self, *, edl_id: str, title: str | None, status: str | None, expected_version: int | None, metadata_patch: dict[str, Any] | None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_edl(edl_id)
            if existing is None:
                raise ProductionNotFoundError(f"EDL {edl_id!r} not found.", context={"edl_id": edl_id})
            values: dict[str, Any] = {}
            if title is not None:
                values["title"] = title.strip()
            if status is not None:
                from ..domain.postproduction.postproduction import PostProductionStatus

                try:
                    PostProductionStatus(status)
                except ValueError as exc:
                    raise ProductionValidationError(f"Unknown EDL status {status!r}.") from exc
                values["status"] = status
            if metadata_patch:
                merged = dict(_load(existing.metadata_json, {}))
                merged.update(metadata_patch)
                values["metadata_json"] = _dump(merged)
            if not values:
                return self._edl_view(existing)
            values["updated_at"] = datetime.now(UTC)
            updated = await store.update_edl(edl_id, values=values)
            if updated is None:
                raise ProductionNotFoundError(f"EDL {edl_id!r} not found.", context={"edl_id": edl_id})
            await scope.record_event(self._events.edl_updated(edl_id, existing.project_id))
            await scope.commit()
            return self._edl_view(updated)

    async def get_edl(self, edl_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_edl(edl_id)
            if row is None:
                raise ProductionNotFoundError(f"EDL {edl_id!r} not found.", context={"edl_id": edl_id})
            return self._edl_view(row)

    async def list_edls(self, project_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_edls(project_id)
            return tuple(self._edl_view(row) for row in rows)
