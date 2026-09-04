"""Application service orchestrating Live Record aggregates.

Every command runs inside one ``TransactionScope`` (platform UoW + outbox),
so domain write + durable event are atomically committed.
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

from ..domain.errors import (
    LiveRecordNotFoundError,
    LiveRecordStaleVersionError,
    LiveRecordValidationError,
)
from ..domain.failure_policy import classify_failure, proposed_transition
from ..domain.lifecycle import LiveExecutionPlanStatus, PlanStatusStateMachine
from ..domain.plan import (
    LiveExecutionPlan,
    PreparedAction,
    RecordingProfile,
    RecordingScene,
)
from ..domain.privacy_scan import scan_live_record_plan
from .events import LiveRecordEventFactory
from .models import (
    DirectorSessionRow,
    LiveExecutionPlanRow,
    RecordingEventRow,
    RecordingSegmentRow,
    RecordingTakeRow,
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


class LiveRecordService:
    def __init__(self, *, scope_factory: Callable[[], TransactionScope], clock: Clock, event_factory: LiveRecordEventFactory, telemetry: Telemetry | None = None) -> None:
        self._scope_factory = scope_factory
        self._clock = clock
        self._events = event_factory
        self._telemetry = telemetry

    # ------------------------------------------------------------------ #
    # Row -> View helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _plan_view(row: LiveExecutionPlanRow) -> Any:
        from .models import LiveExecutionPlanView

        profile = _load(row.recording_profile_json, {})
        scenes = _load(row.scenes_json, [])
        actions = _load(row.actions_json, [])
        bundles = _load(row.payload_bundles_json, {})
        status = row.status
        recordable = status == LiveExecutionPlanStatus.FROZEN.value
        return LiveExecutionPlanView(
            plan_id=row.plan_id,
            episode_id=row.episode_id,
            episode_revision_id=row.episode_revision_id,
            preparation_revision=row.preparation_revision,
            plan_hash=row.plan_hash,
            status=status,
            director_role=row.director_role,
            recording_profile=profile,
            scenes=tuple(scenes),
            actions=tuple(actions),
            payload_bundles=bundles,
            source_workspace_hash=row.source_workspace_hash,
            created_at=_as_utc(row.created_at),
            frozen_at=_as_utc(row.frozen_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
            recordable=recordable,
        )

    @staticmethod
    def _take_view(row: RecordingTakeRow) -> Any:
        from .models import RecordingTakeView

        return RecordingTakeView(
            take_id=row.take_id,
            execution_plan_id=row.execution_plan_id,
            execution_plan_hash=row.execution_plan_hash,
            episode_id=row.episode_id,
            status=row.status,
            started_at=_as_utc(row.started_at),
            ended_at=_as_utc(row.ended_at),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _segment_view(row: RecordingSegmentRow) -> Any:
        from .models import RecordingSegmentView

        return RecordingSegmentView(
            segment_id=row.segment_id,
            take_id=row.take_id,
            segment_index=row.segment_index,
            file_token=row.file_token,
            started_at=_as_utc(row.started_at),
            ended_at=_as_utc(row.ended_at),
            duration_sec=row.duration_sec,
            is_playable=row.is_playable,
            manifest=_load(row.manifest_json, {}),
        )

    @staticmethod
    def _event_view(row: RecordingEventRow) -> Any:
        from .models import RecordingEventView

        return RecordingEventView(
            take_id=row.take_id,
            seq=row.seq,
            event_type=row.event_type,
            t=row.t,
            scene_id=row.scene_id,
            cue_id=row.cue_id,
            action_id=row.action_id,
            segment_id=row.segment_id,
            execution_id=row.execution_id,
            marker_type=row.marker_type,
            detail=row.detail,
            payload=_load(row.payload_json, {}),
            occurred_at=_as_utc(row.occurred_at),
        )

    @staticmethod
    def _director_view(row: DirectorSessionRow) -> Any:
        from .models import DirectorSessionView

        return DirectorSessionView(
            session_id=row.session_id,
            execution_plan_id=row.execution_plan_id,
            execution_plan_hash=row.execution_plan_hash,
            provider_id=row.provider_id,
            model_id=row.model_id,
            connection_state=row.connection_state,
            started_at=_as_utc(row.started_at),
            expires_at=_as_utc(row.expires_at),
            updated_at=_as_utc(row.updated_at),
            metadata=_load(row.metadata_json, {}),
        )

    # ------------------------------------------------------------------ #
    # Domain helpers
    # ------------------------------------------------------------------ #

    def _row_to_domain(self, row: LiveExecutionPlanRow) -> LiveExecutionPlan:
        return LiveExecutionPlan.model_validate({
            "plan_id": row.plan_id,
            "episode_id": row.episode_id,
            "episode_revision_id": row.episode_revision_id,
            "preparation_revision": row.preparation_revision,
            "plan_hash": row.plan_hash,
            "status": LiveExecutionPlanStatus(row.status),
            "created_at": _as_utc(row.created_at) or datetime.now(UTC),
            "frozen_at": _as_utc(row.frozen_at),
            "director_role": row.director_role,
            "recording_profile": _load(row.recording_profile_json, {}),
            "scenes": _load(row.scenes_json, []),
            "actions": _load(row.actions_json, []),
            "payload_bundles": _load(row.payload_bundles_json, {}),
            "source_workspace_hash": row.source_workspace_hash,
            "optimistic_version": row.optimistic_version,
        })

    def _domain_to_row(self, domain: LiveExecutionPlan, *, created_at: datetime | None = None, updated_at: datetime | None = None, metadata: dict[str, Any] | None = None) -> LiveExecutionPlanRow:
        now = datetime.now(UTC)
        return LiveExecutionPlanRow(
            plan_id=domain.plan_id,
            episode_id=domain.episode_id,
            episode_revision_id=domain.episode_revision_id,
            preparation_revision=domain.preparation_revision,
            plan_hash=domain.plan_hash,
            status=domain.status.value,
            director_role=domain.director_role,
            recording_profile_json=_dump(domain.recording_profile.model_dump()),
            scenes_json=_dump([s.model_dump() for s in domain.scenes]),
            actions_json=_dump([a.model_dump() for a in domain.actions]),
            payload_bundles_json=_dump(domain.payload_bundles),
            source_workspace_hash=domain.source_workspace_hash,
            created_at=_as_utc(created_at) or _as_utc(domain.created_at) or now,
            frozen_at=_as_utc(domain.frozen_at),
            updated_at=_as_utc(updated_at) or now,
            optimistic_version=domain.optimistic_version,
            metadata_json=_dump(metadata or {}),
        )

    # ------------------------------------------------------------------ #
    # Plans
    # ------------------------------------------------------------------ #

    async def create_plan(
        self,
        *,
        episode_id: str,
        episode_revision_id: str,
        scenes: tuple[dict[str, Any], ...] = (),
        actions: tuple[dict[str, Any], ...] = (),
        recording_profile: dict[str, Any] | None = None,
        payload_bundles: dict[str, str] | None = None,
        source_workspace_hash: str = "",
        preparation_revision: int | None = None,
        plan_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        episode_id = episode_id.strip()
        episode_revision_id = episode_revision_id.strip()
        if not episode_id:
            raise LiveRecordValidationError("episode_id cannot be blank.")
        if not episode_revision_id:
            raise LiveRecordValidationError("episode_revision_id cannot be blank.")
        # Coerce scenes/actions through domain validation
        coerced_scenes: list[RecordingScene] = []
        for raw in scenes:
            # allow already validated dicts with cues
            if "cues" in raw:
                coerced_scenes.append(RecordingScene.model_validate(raw))
            else:
                # minimal scene without cues -> wrap
                coerced_scenes.append(RecordingScene.model_validate({"scene_id": raw.get("scene_id", f"scene-{len(coerced_scenes)+1:02d}"), "index": raw.get("index", len(coerced_scenes)), "title": raw.get("title", ""), "cues": raw.get("cues", []), "action_ids": raw.get("action_ids", []), **{k: v for k, v in raw.items() if k not in ("scene_id", "index")}}))

        coerced_actions: list[PreparedAction] = []
        for raw in actions:
            coerced_actions.append(PreparedAction.model_validate(raw))

        async with self._scope_factory() as scope:
            store = scope.store()
            rev = preparation_revision
            if rev is None:
                rev = await store.next_preparation_revision(episode_id)
            resolved_plan_id = plan_id or f"plan_{episode_id}_r{rev}"
            # idempotency: if exists return existing
            existing = await store.get_plan(resolved_plan_id)
            if existing is not None:
                return self._plan_view(existing)
            profile = RecordingProfile.model_validate(recording_profile or {})
            domain = LiveExecutionPlan.model_validate({
                "plan_id": resolved_plan_id,
                "episode_id": episode_id,
                "episode_revision_id": episode_revision_id,
                "preparation_revision": rev,
                "recording_profile": profile.model_dump(),
                "scenes": [s.model_dump() for s in coerced_scenes],
                "actions": [a.model_dump() for a in coerced_actions],
                "payload_bundles": payload_bundles or {},
                "source_workspace_hash": source_workspace_hash,
            })
            domain.validate_lineage()
            now = datetime.now(UTC)
            row = LiveExecutionPlanRow(
                plan_id=domain.plan_id,
                episode_id=domain.episode_id,
                episode_revision_id=domain.episode_revision_id,
                preparation_revision=domain.preparation_revision,
                plan_hash=domain.plan_hash,
                status=domain.status.value,
                director_role=domain.director_role,
                recording_profile_json=_dump(domain.recording_profile.model_dump()),
                scenes_json=_dump([s.model_dump() for s in domain.scenes]),
                actions_json=_dump([a.model_dump() for a in domain.actions]),
                payload_bundles_json=_dump(domain.payload_bundles),
                source_workspace_hash=domain.source_workspace_hash,
                created_at=now,
                frozen_at=None,
                updated_at=now,
                optimistic_version=domain.optimistic_version,
                metadata_json=_dump(metadata or {}),
            )
            ok = await store.insert_plan(row)
            if not ok:
                raise LiveRecordValidationError("Plan id collision — retry.", context={"plan_id": resolved_plan_id})
            await scope.record_event(self._events.plan_created(resolved_plan_id, episode_id))
            await scope.commit()
            inserted = await store.get_plan(resolved_plan_id)
            assert inserted is not None
            return self._plan_view(inserted)

    async def update_plan_content(
        self,
        *,
        plan_id: str,
        scenes: tuple[dict[str, Any], ...] | None = None,
        actions: tuple[dict[str, Any], ...] | None = None,
        payload_bundles: dict[str, str] | None = None,
        source_workspace_hash: str | None = None,
        expected_version: int | None = None,
    ) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_plan(plan_id)
            if existing is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(existing)
            coerced_scenes = None
            if scenes is not None:
                coerced_scenes = [RecordingScene.model_validate(s) for s in scenes]
            coerced_actions = None
            if actions is not None:
                coerced_actions = [PreparedAction.model_validate(a) for a in actions]
            updated_domain = domain.edit_content(scenes=coerced_scenes, actions=coerced_actions, payload_bundles=payload_bundles, source_workspace_hash=source_workspace_hash)
            # stale version guard
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise LiveRecordStaleVersionError("Plan optimistic version mismatch.", context={"plan_id": plan_id})
            # persist
            updated = await store.update_plan(
                plan_id,
                status=updated_domain.status.value if updated_domain.status.value != existing.status else None,
                plan_hash=updated_domain.plan_hash if updated_domain.plan_hash != existing.plan_hash else None,
                frozen_at=_as_utc(updated_domain.frozen_at) if updated_domain.frozen_at else None,
                scenes_json=_dump([s.model_dump() for s in updated_domain.scenes]) if scenes is not None else None,
                actions_json=_dump([a.model_dump() for a in updated_domain.actions]) if actions is not None else None,
                payload_bundles_json=_dump(updated_domain.payload_bundles) if payload_bundles is not None else None,
                source_workspace_hash=updated_domain.source_workspace_hash if source_workspace_hash is not None else None,
                optimistic_version=updated_domain.optimistic_version,
                expected_version=expected_version,
            )
            if updated is None:
                raise LiveRecordStaleVersionError("Plan optimistic version mismatch.", context={"plan_id": plan_id})
            await scope.record_event(self._events.plan_updated(plan_id))
            await scope.commit()
            return self._plan_view(updated)

    async def transition_plan(self, *, plan_id: str, target: str, expected_version: int | None = None, current_episode_revision_id: str | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_plan(plan_id)
            if existing is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(existing)
            if current_episode_revision_id is not None:
                reason = domain.staleness_reason(current_episode_revision_id)
                if reason:
                    raise LiveRecordValidationError(reason, context={"plan_id": plan_id})
            target_upper = target.upper()
            try:
                target_status = LiveExecutionPlanStatus(target_upper)
            except ValueError as exc:
                raise LiveRecordValidationError(f"Unknown plan target {target!r}.") from exc
            # derive transition via domain methods for side effects (hash, frozen_at)
            prev_status = domain.status
            if target_status == LiveExecutionPlanStatus.PREPARED:
                updated_domain = domain.mark_prepared()
            elif target_status == LiveExecutionPlanStatus.VALIDATED:
                updated_domain = domain.mark_validated()
            elif target_status == LiveExecutionPlanStatus.FROZEN:
                updated_domain = domain.freeze()
            elif target_status == LiveExecutionPlanStatus.STALE:
                updated_domain = domain.mark_stale()
            elif target_status == LiveExecutionPlanStatus.INVALID:
                updated_domain = domain.mark_invalid()
            else:
                # generic fallback
                updated_domain = domain.model_copy(update={"status": PlanStatusStateMachine.transition(domain.status, target_status), "optimistic_version": domain.optimistic_version + 1})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise LiveRecordStaleVersionError("Plan optimistic version mismatch.", context={"plan_id": plan_id})
            updated = await store.update_plan(
                plan_id,
                status=updated_domain.status.value,
                plan_hash=updated_domain.plan_hash,
                frozen_at=_as_utc(updated_domain.frozen_at),
                optimistic_version=updated_domain.optimistic_version,
                expected_version=expected_version,
            )
            if updated is None:
                raise LiveRecordStaleVersionError("Plan optimistic version mismatch.", context={"plan_id": plan_id})
            # events
            if updated_domain.status == LiveExecutionPlanStatus.FROZEN and prev_status != LiveExecutionPlanStatus.FROZEN:
                await scope.record_event(self._events.plan_frozen(plan_id, updated_domain.plan_hash))
            else:
                await scope.record_event(self._events.plan_transitioned(plan_id, prev_status.value, updated_domain.status.value))
            await scope.commit()
            return self._plan_view(updated)

    async def get_plan(self, plan_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_plan(plan_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            return self._plan_view(row)

    async def list_plans(self, episode_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_plans(episode_id)
            return tuple(self._plan_view(row) for row in rows)

    async def staleness_check(self, *, plan_id: str, current_episode_revision_id: str) -> dict[str, Any]:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_plan(plan_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(row)
            reason = domain.staleness_reason(current_episode_revision_id)
            if reason:
                raise LiveRecordValidationError(reason, context={"plan_id": plan_id})
            return {"plan_id": plan_id, "stale": False, "episode_revision_id": row.episode_revision_id, "current_episode_revision_id": current_episode_revision_id}

    # ------------------------------------------------------------------ #
    # Preparation package
    # ------------------------------------------------------------------ #

    async def prepare_recording_package(self, *, episode_id: str, episode_revision_id: str, scenes: tuple[dict[str, Any], ...] = (), recording_profile: dict[str, Any] | None = None, source_workspace_hash: str = "", payload: dict[str, Any] | None = None) -> Any:
        from ..domain.preparation import (
            EpisodePreparationInput,
            RecordingPreparationBuilder,
            ScenePreparationInput,
        )

        prep_scenes: list[ScenePreparationInput] = []
        for raw in scenes:
            prep_scenes.append(ScenePreparationInput(title=raw.get("title", ""), narration_source=raw.get("narration_source", ""), narration_text=raw.get("narration_text"), duration_sec=float(raw.get("duration_sec", 0) or 0), expected_result=raw.get("expected_result", {}), actions=list(raw.get("actions", []))))
        inp = EpisodePreparationInput(episode_id=episode_id, episode_revision_id=episode_revision_id, source_workspace_hash=source_workspace_hash, recording_profile=recording_profile, scenes=prep_scenes)
        async with self._scope_factory() as scope:
            store = scope.store()
            rev = await store.next_preparation_revision(episode_id)
            plan = RecordingPreparationBuilder.build_plan(inp, preparation_revision=rev)
            existing = await store.get_plan(plan.plan_id)
            if existing is not None:
                return self._plan_view(existing)
            now = datetime.now(UTC)
            row = LiveExecutionPlanRow(
                plan_id=plan.plan_id,
                episode_id=plan.episode_id,
                episode_revision_id=plan.episode_revision_id,
                preparation_revision=plan.preparation_revision,
                plan_hash=plan.plan_hash,
                status=plan.status.value,
                director_role=plan.director_role,
                recording_profile_json=_dump(plan.recording_profile.model_dump()),
                scenes_json=_dump([s.model_dump() for s in plan.scenes]),
                actions_json=_dump([a.model_dump() for a in plan.actions]),
                payload_bundles_json=_dump(plan.payload_bundles),
                source_workspace_hash=plan.source_workspace_hash,
                created_at=now,
                frozen_at=None,
                updated_at=now,
                optimistic_version=plan.optimistic_version,
                metadata_json=_dump(payload or {}),
            )
            ok = await store.insert_plan(row)
            if not ok:
                raise LiveRecordValidationError("Preparation plan collision — retry.")
            await scope.record_event(self._events.plan_created(plan.plan_id, episode_id))
            await scope.commit()
            inserted = await store.get_plan(plan.plan_id)
            assert inserted is not None
            return self._plan_view(inserted)

    # ------------------------------------------------------------------ #
    # Takes
    # ------------------------------------------------------------------ #

    async def create_take(self, *, plan_id: str, episode_id: str | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            plan_row = await store.get_plan(plan_id)
            if plan_row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(plan_row)
            domain.assert_usable_for_recording(domain.episode_revision_id)
            # count existing takes for id generation
            existing_takes = await store.list_takes(plan_id)
            seq = len(existing_takes) + 1
            take_id = f"take_{plan_row.episode_id}_{seq}"
            # idempotency: if take with same id exists return it
            existing_take = await store.get_take(take_id)
            if existing_take is not None:
                return self._take_view(existing_take)
            now = datetime.now(UTC)
            row = RecordingTakeRow(
                take_id=take_id,
                execution_plan_id=plan_row.plan_id,
                execution_plan_hash=plan_row.plan_hash,
                episode_id=plan_row.episode_id if episode_id is None else episode_id,
                status="IDLE",
                started_at=None,
                ended_at=None,
                created_at=now,
                updated_at=now,
                optimistic_version=0,
                metadata_json=_dump({"created_via": "api"}),
            )
            ok = await store.insert_take(row)
            if not ok:
                raise LiveRecordValidationError("Take id collision — retry.")
            await scope.record_event(self._events.take_created(take_id, plan_id))
            await scope.commit()
            inserted = await store.get_take(take_id)
            assert inserted is not None
            return self._take_view(inserted)

    async def get_take(self, take_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_take(take_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            return self._take_view(row)

    async def list_takes(self, execution_plan_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_takes(execution_plan_id)
            return tuple(self._take_view(row) for row in rows)

    async def transition_take(self, *, take_id: str, target_status: str, expected_version: int | None = None) -> Any:
        from ..domain.lifecycle import TakeSessionStatus, TakeStatusStateMachine

        try:
            target = TakeSessionStatus(target_status)
        except ValueError as exc:
            raise LiveRecordValidationError(f"Unknown take status {target_status!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_take(take_id)
            if existing is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            current = TakeSessionStatus(existing.status)
            TakeStatusStateMachine.transition(current, target)
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise LiveRecordStaleVersionError("Take optimistic version mismatch.", context={"take_id": take_id})
            prev_status = existing.status
            updated = await store.update_take(take_id, status=target.value, optimistic_version=existing.optimistic_version + 1, expected_version=expected_version)
            if updated is None:
                raise LiveRecordStaleVersionError("Take optimistic version mismatch.", context={"take_id": take_id})
            await scope.record_event(self._events.take_transitioned(take_id, prev_status, target.value))
            await scope.commit()
            return self._take_view(updated)

    # ------------------------------------------------------------------ #
    # Segments
    # ------------------------------------------------------------------ #

    async def create_segment(
        self,
        *,
        take_id: str,
        segment_index: int = 0,
        file_token: str = "",
        started_at: str | None = None,
        ended_at: str | None = None,
        duration_sec: float | None = None,
        is_playable: bool = False,
        manifest: dict[str, Any] | None = None,
        segment_id: str | None = None,
    ) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            take = await store.get_take(take_id)
            if take is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            resolved_id = segment_id or f"{take_id}_seg{segment_index:04d}"
            now = datetime.now(UTC)
            # parse datetimes
            def _parse(dt_str: str | None) -> datetime | None:
                if not dt_str:
                    return None
                try:
                    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except ValueError:
                    return None

            row = RecordingSegmentRow(
                segment_id=resolved_id,
                take_id=take_id,
                segment_index=segment_index,
                file_token=file_token,
                started_at=_parse(started_at) or now,
                ended_at=_parse(ended_at),
                duration_sec=duration_sec,
                is_playable=is_playable,
                manifest_json=_dump(manifest or {}),
            )
            # upsert semantics: if exists return existing
            existing = await store.get_segment(resolved_id)
            if existing is not None:
                # update via upsert
                saved = await store.upsert_segment(row)
                await scope.commit()
                return self._segment_view(saved)
            ok = await store.insert_segment(row)
            if not ok:
                saved = await store.upsert_segment(row)
                await scope.commit()
                return self._segment_view(saved)
            await scope.record_event(self._events.segment_created(resolved_id, take_id))
            await scope.commit()
            inserted = await store.get_segment(resolved_id)
            assert inserted is not None
            return self._segment_view(inserted)

    async def list_segments(self, take_id: str) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            take = await store.get_take(take_id)
            if take is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            rows = await store.list_segments(take_id)
            return tuple(self._segment_view(row) for row in rows)

    async def get_segment(self, segment_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_segment(segment_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Segment {segment_id!r} not found.", context={"segment_id": segment_id})
            return self._segment_view(row)

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    async def append_event(
        self,
        *,
        take_id: str,
        event_type: str,
        t: float = 0.0,
        scene_id: str | None = None,
        cue_id: str | None = None,
        action_id: str | None = None,
        segment_id: str | None = None,
        execution_id: str | None = None,
        marker_type: str | None = None,
        detail: str = "",
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if not event_type.strip():
            raise LiveRecordValidationError("event_type cannot be blank.")
        async with self._scope_factory() as scope:
            store = scope.store()
            take = await store.get_take(take_id)
            if take is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            # next seq
            existing = await store.list_events(take_id)
            seq = len(existing)
            now = datetime.now(UTC)
            row = RecordingEventRow(
                take_id=take_id,
                seq=seq,
                event_type=event_type,
                t=t,
                scene_id=scene_id,
                cue_id=cue_id,
                action_id=action_id,
                segment_id=segment_id,
                execution_id=execution_id,
                marker_type=marker_type,
                detail=detail,
                payload_json=_dump(payload or {}),
                occurred_at=now,
            )
            saved = await store.append_event(row)
            await scope.record_event(self._events.event_appended(take_id, seq, event_type))
            await scope.commit()
            return self._event_view(saved)

    async def list_events(self, take_id: str) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            take = await store.get_take(take_id)
            if take is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            rows = await store.list_events(take_id)
            return tuple(self._event_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Director sessions
    # ------------------------------------------------------------------ #

    async def bootstrap_director_session(
        self,
        *,
        execution_plan_id: str,
        episode_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        connection_state: str = "CONNECTING",
    ) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            plan_row = await store.get_plan(execution_plan_id)
            if plan_row is None:
                raise LiveRecordNotFoundError(f"Plan {execution_plan_id!r} not found.", context={"plan_id": execution_plan_id})
            domain = self._row_to_domain(plan_row)
            domain.assert_usable_for_recording(domain.episode_revision_id)
            if episode_id is not None and plan_row.episode_id != episode_id:
                raise LiveRecordValidationError(f"Episode mismatch: plan bound to {plan_row.episode_id!r}, got {episode_id!r}.")
            session_id = _new_id("ldir_")
            now = datetime.now(UTC)
            # token is handled at API layer; here we just create session record
            # compute expiry 30min from now if not provided
            expires_at = datetime.fromtimestamp(now.timestamp() + 1800, tz=UTC)
            # token hash placeholder
            token_hash = hashlib.sha256(f"{session_id}:{plan_row.plan_hash}".encode()).hexdigest()[:16]
            metadata = {"token_hash": token_hash, "episode_id": plan_row.episode_id}
            row = DirectorSessionRow(
                session_id=session_id,
                execution_plan_id=execution_plan_id,
                execution_plan_hash=plan_row.plan_hash,
                provider_id=provider_id,
                model_id=model_id,
                connection_state=connection_state,
                started_at=now,
                expires_at=expires_at,
                updated_at=now,
                metadata_json=_dump(metadata),
            )
            ok = await store.insert_director_session(row)
            if not ok:
                raise LiveRecordValidationError("Director session collision — retry.")
            await scope.record_event(self._events.director_session_created(session_id, execution_plan_id))
            await scope.commit()
            inserted = await store.get_director_session(session_id)
            assert inserted is not None
            view = self._director_view(inserted)
            # return with token info for API to mint real token
            payload = view.to_payload()
            payload["token"] = f"live-record-token-{session_id}"
            payload["expires_at"] = expires_at.isoformat()
            return payload

    async def get_director_session(self, session_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_director_session(session_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Director session {session_id!r} not found.", context={"session_id": session_id})
            return self._director_view(row)

    async def refresh_director_session(self, *, session_id: str, connection_state: str | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_director_session(session_id)
            if existing is None:
                raise LiveRecordNotFoundError(f"Director session {session_id!r} not found.", context={"session_id": session_id})
            plan_row = await store.get_plan(existing.execution_plan_id)
            if plan_row is None:
                raise LiveRecordNotFoundError(f"Plan {existing.execution_plan_id!r} not found for session.", context={"plan_id": existing.execution_plan_id})
            domain = self._row_to_domain(plan_row)
            domain.assert_usable_for_recording(plan_row.episode_revision_id)
            now = datetime.now(UTC)
            expires_at = datetime.fromtimestamp(now.timestamp() + 1800, tz=UTC)
            metadata = _load(existing.metadata_json, {})
            metadata["refresh_count"] = int(metadata.get("refresh_count", 0)) + 1
            updated = await store.update_director_session(session_id, connection_state=connection_state, expires_at=expires_at, metadata_json=_dump(metadata))
            if updated is None:
                raise LiveRecordNotFoundError(f"Director session {session_id!r} not found.", context={"session_id": session_id})
            await scope.record_event(self._events.director_session_refreshed(session_id))
            await scope.commit()
            view = self._director_view(updated)
            payload = view.to_payload()
            payload["token"] = f"live-record-token-{session_id}-refreshed-{metadata['refresh_count']}"
            payload["expires_at"] = expires_at.isoformat()
            payload["refreshed"] = True
            return payload

    async def list_director_sessions(self, execution_plan_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_director_sessions(execution_plan_id)
            return tuple(self._director_view(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Privacy scan + failure classification + action dispatch
    # ------------------------------------------------------------------ #

    async def scan_privacy(self, *, plan_id: str, extra_secret_values: list[str] | None = None) -> dict[str, Any]:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_plan(plan_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(row)
            report = scan_live_record_plan(payload_bundles=domain.payload_bundles, scenes=domain.scenes, actions=domain.actions, extra_secret_values=extra_secret_values)
            result = report.to_dict()
            result["plan_id"] = row.plan_id
            result["plan_status"] = row.status
            # audit event not required for commit? but we record privacy scan completed
            await scope.record_event(self._events.privacy_scan_completed(plan_id, report.status))
            await scope.commit()
            return result

    async def classify_failure(self, *, failure: str) -> dict[str, Any]:
        policy = classify_failure(failure)
        return {"failure": failure, "policy": {"failure": policy.failure, "failure_class": policy.failure_class.value, "action": policy.action.value}, "proposed_transition": proposed_transition(policy)}

    async def prepare_action_dispatch(self, *, plan_id: str, action_id: str) -> dict[str, Any]:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_plan(plan_id)
            if row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(row)
            if not PlanStatusStateMachine.is_frozen(domain.status):
                from ..domain.errors import LiveRecordNotFrozenError

                raise LiveRecordNotFrozenError(f"ACTION_DISPATCH_NOT_FROZEN: plan status={domain.status.value}.", context={"plan_id": plan_id, "status": domain.status.value})
            action = next((a for a in domain.actions if a.action_id == action_id), None)
            if action is None:
                raise LiveRecordNotFoundError(f"ACTION_NOT_IN_PLAN: action '{action_id}' is not part of plan '{plan_id}'.", context={"plan_id": plan_id, "action_id": action_id})
            payload_text = domain.payload_bundles.get(action.action_id)
            if action.type == "CODE_PLAYBACK" and payload_text is None:
                raise LiveRecordValidationError(f"PAYLOAD_BUNDLE_MISSING: no prepared payload bundle for action '{action.action_id}'.", context={"action_id": action.action_id})
            return {"plan_id": domain.plan_id, "plan_hash": domain.plan_hash, "action": action.model_dump(mode="json"), "payload_text": payload_text, "expected_after": action.expected_after.model_dump(mode="json") if action.expected_after else None}

    async def record_action_result(
        self,
        *,
        plan_id: str,
        take_id: str,
        action_id: str,
        status: str,
        execution_id: str,
        idempotency_key: str,
        t: float = 0.0,
        detail: str = "",
        before_hash_observed: str | None = None,
        after_hash_observed: str | None = None,
        observed: dict[str, Any] | None = None,
        scene_id: str | None = None,
        cue_id: str | None = None,
    ) -> dict[str, Any]:
        async with self._scope_factory() as scope:
            store = scope.store()
            plan_row = await store.get_plan(plan_id)
            if plan_row is None:
                raise LiveRecordNotFoundError(f"Plan {plan_id!r} not found.", context={"plan_id": plan_id})
            domain = self._row_to_domain(plan_row)
            if not PlanStatusStateMachine.is_frozen(domain.status):
                from ..domain.errors import LiveRecordNotFrozenError

                raise LiveRecordNotFrozenError(f"ACTION_RESULT_NOT_FROZEN: plan status={domain.status.value}.", context={"plan_id": plan_id})
            action = next((a for a in domain.actions if a.action_id == action_id), None)
            if action is None:
                raise LiveRecordNotFoundError(f"ACTION_NOT_IN_PLAN: action '{action_id}' is not part of plan '{plan_id}'.", context={"plan_id": plan_id, "action_id": action_id})
            take = await store.get_take(take_id)
            if take is None:
                raise LiveRecordNotFoundError(f"Take {take_id!r} not found.", context={"take_id": take_id})
            if take.execution_plan_id != domain.plan_id:
                raise LiveRecordValidationError("TAKE_PLAN_MISMATCH: take does not belong to this plan.", context={"take_id": take_id, "plan_id": plan_id})
            verification: dict[str, Any] = {"verified": True, "checks": []}
            event_type = "ACTION_SUCCESS" if status == "SUCCESS" else "ACTION_FAILURE"
            if action.type == "CODE_PLAYBACK":
                checks = verification["checks"]
                if action.before_hash is not None:
                    ok = before_hash_observed == action.before_hash
                    checks.append({"check": "before_hash", "ok": ok})
                    if not ok:
                        verification["verified"] = False
                if action.after_hash is not None:
                    ok = after_hash_observed == action.after_hash
                    checks.append({"check": "after_hash", "ok": ok})
                    if not ok:
                        verification["verified"] = False
                if not verification["verified"]:
                    event_type = "ACTION_TAMPERED"
            existing_events = await store.list_events(take_id)
            seq = len(existing_events)
            now = datetime.now(UTC)
            row = RecordingEventRow(
                take_id=take_id,
                seq=seq,
                event_type=event_type,
                t=t,
                scene_id=scene_id or action.scene_id,
                cue_id=cue_id or action.cue_id,
                action_id=action.action_id,
                execution_id=execution_id,
                detail=detail,
                payload_json=_dump({"status": status, "verification": verification, "idempotency_key": idempotency_key, **(observed or {})}),
                occurred_at=now,
                segment_id=None,
                marker_type=None,
            )
            saved = await store.append_event(row)
            await scope.record_event(self._events.event_appended(take_id, seq, event_type))
            await scope.commit()
            from .models import RecordingEventView

            view = RecordingEventView(
                take_id=saved.take_id,
                seq=saved.seq,
                event_type=saved.event_type,
                t=saved.t,
                scene_id=saved.scene_id,
                cue_id=saved.cue_id,
                action_id=saved.action_id,
                segment_id=saved.segment_id,
                execution_id=saved.execution_id,
                marker_type=saved.marker_type,
                detail=saved.detail,
                payload=_load(saved.payload_json, {}),
                occurred_at=_as_utc(saved.occurred_at),
            )
            return {"event": view.to_payload(), "verification": verification}
