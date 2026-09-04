"""Handlers connecting commands/queries to LiveRecordService."""

from __future__ import annotations

from typing import Any

from .commands import (
    AppendTakeEvent,
    BootstrapDirectorSession,
    CreateExecutionPlan,
    CreateSegment,
    CreateTake,
    DispatchPreparedAction,
    PrepareRecordingPackage,
    RecordActionResult,
    RefreshDirectorSession,
    TransitionPlan,
    UpdatePlanContent,
)
from .queries import (
    ClassifyFailure,
    GetDirectorSession,
    GetLiveExecutionPlan,
    GetTake,
    ListDirectorSessions,
    ListLiveExecutionPlans,
    ListTakeEvents,
    ListTakes,
    ListTakeSegments,
    PrivacyScan,
    StalenessCheck,
)
from .runtime import LiveRecordServices, container_for


class _Handler:
    def __init__(self, services: LiveRecordServices | None = None) -> None:
        self._services = services


class CreateExecutionPlanHandler(_Handler):
    async def handle(self, command: CreateExecutionPlan) -> Any:
        return await container_for(self._services).live_record.create_plan(
            episode_id=command.episode_id,
            episode_revision_id=command.episode_revision_id,
            scenes=command.scenes,
            actions=command.actions,
            recording_profile=command.recording_profile,
            payload_bundles=command.payload_bundles,
            source_workspace_hash=command.source_workspace_hash,
            preparation_revision=command.preparation_revision,
            plan_id=command.plan_id,
            metadata=command.metadata,
        )


class UpdatePlanContentHandler(_Handler):
    async def handle(self, command: UpdatePlanContent) -> Any:
        return await container_for(self._services).live_record.update_plan_content(
            plan_id=command.plan_id, scenes=command.scenes, actions=command.actions, payload_bundles=command.payload_bundles, source_workspace_hash=command.source_workspace_hash, expected_version=command.expected_version
        )


class TransitionPlanHandler(_Handler):
    async def handle(self, command: TransitionPlan) -> Any:
        return await container_for(self._services).live_record.transition_plan(plan_id=command.plan_id, target=command.target, expected_version=command.expected_version, current_episode_revision_id=command.current_episode_revision_id)


class GetLiveExecutionPlanHandler(_Handler):
    async def handle(self, query: GetLiveExecutionPlan) -> Any:
        return await container_for(self._services).live_record.get_plan(query.plan_id)


class ListLiveExecutionPlansHandler(_Handler):
    async def handle(self, query: ListLiveExecutionPlans) -> Any:
        return await container_for(self._services).live_record.list_plans(query.episode_id)


class StalenessCheckHandler(_Handler):
    async def handle(self, query: StalenessCheck) -> Any:
        return await container_for(self._services).live_record.staleness_check(plan_id=query.plan_id, current_episode_revision_id=query.current_episode_revision_id)


class PrepareRecordingPackageHandler(_Handler):
    async def handle(self, command: PrepareRecordingPackage) -> Any:
        return await container_for(self._services).live_record.prepare_recording_package(episode_id=command.episode_id, episode_revision_id=command.episode_revision_id, scenes=command.scenes, recording_profile=command.recording_profile, source_workspace_hash=command.source_workspace_hash, payload=command.payload)


class CreateTakeHandler(_Handler):
    async def handle(self, command: CreateTake) -> Any:
        return await container_for(self._services).live_record.create_take(plan_id=command.plan_id, episode_id=command.episode_id)


class GetTakeHandler(_Handler):
    async def handle(self, query: GetTake) -> Any:
        return await container_for(self._services).live_record.get_take(query.take_id)


class ListTakesHandler(_Handler):
    async def handle(self, query: ListTakes) -> Any:
        return await container_for(self._services).live_record.list_takes(query.execution_plan_id)


class AppendTakeEventHandler(_Handler):
    async def handle(self, command: AppendTakeEvent) -> Any:
        return await container_for(self._services).live_record.append_event(
            take_id=command.take_id, event_type=command.event_type, t=command.t, scene_id=command.scene_id, cue_id=command.cue_id, action_id=command.action_id, segment_id=command.segment_id, execution_id=command.execution_id, marker_type=command.marker_type, detail=command.detail, payload=command.payload
        )


class ListTakeEventsHandler(_Handler):
    async def handle(self, query: ListTakeEvents) -> Any:
        return await container_for(self._services).live_record.list_events(query.take_id)


class CreateSegmentHandler(_Handler):
    async def handle(self, command: CreateSegment) -> Any:
        return await container_for(self._services).live_record.create_segment(take_id=command.take_id, segment_index=command.segment_index, file_token=command.file_token, started_at=command.started_at, ended_at=command.ended_at, duration_sec=command.duration_sec, is_playable=command.is_playable, manifest=command.manifest, segment_id=command.segment_id)


class ListTakeSegmentsHandler(_Handler):
    async def handle(self, query: ListTakeSegments) -> Any:
        return await container_for(self._services).live_record.list_segments(query.take_id)


class BootstrapDirectorSessionHandler(_Handler):
    async def handle(self, command: BootstrapDirectorSession) -> Any:
        return await container_for(self._services).live_record.bootstrap_director_session(execution_plan_id=command.execution_plan_id, episode_id=command.episode_id, provider_id=command.provider_id, model_id=command.model_id, connection_state=command.connection_state)


class GetDirectorSessionHandler(_Handler):
    async def handle(self, query: GetDirectorSession) -> Any:
        return await container_for(self._services).live_record.get_director_session(query.session_id)


class ListDirectorSessionsHandler(_Handler):
    async def handle(self, query: ListDirectorSessions) -> Any:
        return await container_for(self._services).live_record.list_director_sessions(query.execution_plan_id)


class RefreshDirectorSessionHandler(_Handler):
    async def handle(self, command: RefreshDirectorSession) -> Any:
        return await container_for(self._services).live_record.refresh_director_session(session_id=command.session_id, connection_state=command.connection_state)


class PrivacyScanHandler(_Handler):
    async def handle(self, query: PrivacyScan) -> Any:
        return await container_for(self._services).live_record.scan_privacy(plan_id=query.plan_id)


class ClassifyFailureHandler(_Handler):
    async def handle(self, query: ClassifyFailure) -> Any:
        return await container_for(self._services).live_record.classify_failure(failure=query.failure)


class DispatchPreparedActionHandler(_Handler):
    async def handle(self, command: DispatchPreparedAction) -> Any:
        return await container_for(self._services).live_record.prepare_action_dispatch(plan_id=command.plan_id, action_id=command.action_id)


class RecordActionResultHandler(_Handler):
    async def handle(self, command: RecordActionResult) -> Any:
        return await container_for(self._services).live_record.record_action_result(
            plan_id=command.plan_id,
            take_id=command.take_id,
            action_id=command.action_id,
            status=command.status,
            execution_id=command.execution_id,
            idempotency_key=command.idempotency_key,
            t=command.t,
            detail=command.detail,
            before_hash_observed=command.before_hash_observed,
            after_hash_observed=command.after_hash_observed,
            observed=command.observed,
            scene_id=command.scene_id,
            cue_id=command.cue_id,
        )
