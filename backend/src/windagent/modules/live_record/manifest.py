"""Module manifest for Live Record (Phase 17)."""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_live_record_router
from .application.commands import (
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
from .application.handlers import (
    AppendTakeEventHandler,
    BootstrapDirectorSessionHandler,
    ClassifyFailureHandler,
    CreateExecutionPlanHandler,
    CreateSegmentHandler,
    CreateTakeHandler,
    DispatchPreparedActionHandler,
    GetDirectorSessionHandler,
    GetLiveExecutionPlanHandler,
    GetTakeHandler,
    ListDirectorSessionsHandler,
    ListLiveExecutionPlansHandler,
    ListTakeEventsHandler,
    ListTakeSegmentsHandler,
    ListTakesHandler,
    PrepareRecordingPackageHandler,
    PrivacyScanHandler,
    RecordActionResultHandler,
    RefreshDirectorSessionHandler,
    StalenessCheckHandler,
    TransitionPlanHandler,
    UpdatePlanContentHandler,
)
from .application.queries import (
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
from .application.runtime import LiveRecordServices
from .jobs.handlers import DirectorHeartbeatJobHandler, SegmentFinalizeJobHandler

LIVE_RECORD_JOB_TYPES = (
    "live_record.director.heartbeat",
    "live_record.segment.finalize",
)


def build_live_record_manifest(services: LiveRecordServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateExecutionPlan, CreateExecutionPlanHandler(services)),
            CommandRegistration(UpdatePlanContent, UpdatePlanContentHandler(services)),
            CommandRegistration(TransitionPlan, TransitionPlanHandler(services)),
            CommandRegistration(PrepareRecordingPackage, PrepareRecordingPackageHandler(services)),
            CommandRegistration(CreateTake, CreateTakeHandler(services)),
            CommandRegistration(AppendTakeEvent, AppendTakeEventHandler(services)),
            CommandRegistration(CreateSegment, CreateSegmentHandler(services)),
            CommandRegistration(BootstrapDirectorSession, BootstrapDirectorSessionHandler(services)),
            CommandRegistration(RefreshDirectorSession, RefreshDirectorSessionHandler(services)),
            CommandRegistration(DispatchPreparedAction, DispatchPreparedActionHandler(services)),
            CommandRegistration(RecordActionResult, RecordActionResultHandler(services)),
        ),
        queries=(
            QueryRegistration(GetLiveExecutionPlan, GetLiveExecutionPlanHandler(services)),
            QueryRegistration(ListLiveExecutionPlans, ListLiveExecutionPlansHandler(services)),
            QueryRegistration(GetTake, GetTakeHandler(services)),
            QueryRegistration(ListTakes, ListTakesHandler(services)),
            QueryRegistration(ListTakeEvents, ListTakeEventsHandler(services)),
            QueryRegistration(ListTakeSegments, ListTakeSegmentsHandler(services)),
            QueryRegistration(GetDirectorSession, GetDirectorSessionHandler(services)),
            QueryRegistration(ListDirectorSessions, ListDirectorSessionsHandler(services)),
            QueryRegistration(PrivacyScan, PrivacyScanHandler(services)),
            QueryRegistration(ClassifyFailure, ClassifyFailureHandler(services)),
            QueryRegistration(StalenessCheck, StalenessCheckHandler(services)),
        ),
        jobs=(
            JobRegistration("live_record.director.heartbeat", DirectorHeartbeatJobHandler(services)),
            JobRegistration("live_record.segment.finalize", SegmentFinalizeJobHandler(services)),
        ),
        routers=(create_live_record_router(),),
        capabilities=("live_record", "plans", "sessions", "takes", "cues", "director", "preparation"),
    )


manifest = build_live_record_manifest()
