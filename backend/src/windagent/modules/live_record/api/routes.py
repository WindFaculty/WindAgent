"""HTTP surface of Live Record (mounted under ``/api/v4``)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field

from windagent.kernel.time import utc_now
from windagent.platform.observability import current_operation_context
from windagent.platform.security import (
    AuditEvent,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    SecretStore,
)

from ..application import queries as app_queries
from ..application.commands import (
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
from ..application.runtime import LiveRecordServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "live_record"
MODULE_VERSION = "1.0.0"
LIVE_RECORD_PREFIX = "/live-record"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "live_record.read"
WRITE_ACTION = "live_record.write"
RESOURCE_TYPE = "live_record"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class CreatePlanIn(BaseModel):
    episode_id: str = Field(min_length=1, max_length=64)
    episode_revision_id: str = Field(min_length=1, max_length=64)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    recording_profile: dict[str, Any] | None = None
    payload_bundles: dict[str, str] = Field(default_factory=dict)
    source_workspace_hash: str = Field(default="", max_length=64)
    plan_id: str | None = Field(default=None, max_length=64)
    preparation_revision: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdatePlanContentIn(BaseModel):
    scenes: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    payload_bundles: dict[str, str] | None = None
    source_workspace_hash: str | None = Field(default=None, max_length=64)
    expected_version: int | None = Field(default=None, ge=0)


class TransitionPlanIn(BaseModel):
    target: str = Field(min_length=1, max_length=20)
    expected_version: int | None = Field(default=None, ge=0)
    current_episode_revision_id: str | None = Field(default=None, max_length=64)


class PreparePackageIn(BaseModel):
    episode_id: str = Field(min_length=1, max_length=64)
    episode_revision_id: str = Field(min_length=1, max_length=64)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    recording_profile: dict[str, Any] | None = None
    source_workspace_hash: str = Field(default="", max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class CreateTakeIn(BaseModel):
    episode_id: str | None = Field(default=None, max_length=64)


class AppendEventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=48)
    t: float = Field(default=0.0, ge=0)
    scene_id: str | None = Field(default=None, max_length=64)
    cue_id: str | None = Field(default=None, max_length=64)
    action_id: str | None = Field(default=None, max_length=64)
    segment_id: str | None = Field(default=None, max_length=64)
    execution_id: str | None = Field(default=None, max_length=64)
    marker_type: str | None = Field(default=None, max_length=64)
    detail: str = Field(default="", max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class CreateSegmentIn(BaseModel):
    segment_index: int = Field(default=0, ge=0)
    file_token: str = Field(default="", max_length=255)
    started_at: str | None = None
    ended_at: str | None = None
    duration_sec: float | None = Field(default=None, ge=0)
    is_playable: bool = Field(default=False)
    manifest: dict[str, Any] = Field(default_factory=dict)
    segment_id: str | None = Field(default=None, max_length=64)


class BootstrapDirectorSessionIn(BaseModel):
    episode_id: str | None = Field(default=None, max_length=64)
    provider_id: str | None = Field(default=None, max_length=64)
    model_id: str | None = Field(default=None, max_length=128)
    connection_state: str = Field(default="CONNECTING", max_length=32)


class RefreshDirectorSessionIn(BaseModel):
    connection_state: str | None = Field(default=None, max_length=32)


class RecordActionResultIn(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    execution_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=100)
    t: float = Field(default=0.0, ge=0)
    detail: str = Field(default="", max_length=2000)
    before_hash_observed: str | None = Field(default=None, max_length=64)
    after_hash_observed: str | None = Field(default=None, max_length=64)
    observed: dict[str, Any] = Field(default_factory=dict)
    scene_id: str | None = Field(default=None, max_length=64)
    cue_id: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------- #
# Policy + ambient services scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_live_record_policy(action: str, resource_type: str = RESOURCE_TYPE) -> Callable[[Request], Awaitable[PolicyDecision]]:
    normalized_action = action

    async def dependency(request: Request) -> PolicyDecision:
        engine = getattr(request.app.state, "policy_engine", None)
        if engine is None:
            return PolicyDecision(effect=PolicyEffect.ALLOW, reason="no policy engine is configured", policy_id=POLICY_UNCONFIGURED_POLICY_ID)
        decision = await cast(PolicyEngine, engine).decide(PolicyRequest(action=normalized_action, resource_type=resource_type, actor_id=_principal_actor_id(request)))  # type: ignore[arg-type]
        await _audit_decision(request, decision, normalized_action, resource_type)
        if decision.effect is not PolicyEffect.ALLOW:
            from windagent.kernel.errors import DomainError

            raise DomainError(decision.reason or "denied by policy", code="forbidden", context={"policy_id": decision.policy_id})
        return decision

    return dependency


async def _audit_decision(request: Request, decision: PolicyDecision, action: str, resource_type: str) -> None:
    sink = getattr(request.app.state, "audit_sink", None)
    if sink is None:
        return
    operation = current_operation_context()
    await sink.record(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            outcome=decision.effect.value,
            actor_id=_principal_actor_id(request),  # type: ignore[arg-type]
            correlation_id=operation.correlation_id if operation else None,
            causation_id=operation.causation_id if operation else None,
            trace_id=operation.trace_id if operation else None,
            reason=decision.reason,
            details={"policy_id": decision.policy_id} if decision.policy_id else {},
            occurred_at=utc_now(),
        )
    )


def services_from_state(request: Request) -> LiveRecordServices:
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="live_record requires a configured database")
    from windagent.platform.security import EnvironmentSecretStore

    return LiveRecordServices(scope_factory=sql_scope_factory(database), secrets=cast(SecretStore, EnvironmentSecretStore()), telemetry=getattr(request.app.state, "telemetry", None))


async def services_scope(request: Request) -> AsyncIterator[None]:
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_live_record_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_live_record_policy(WRITE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    return request.app.state.command_bus, request.app.state.query_bus


def create_live_record_router() -> APIRouter:
    router = APIRouter(prefix=LIVE_RECORD_PREFIX, tags=["live-record"])

    # -- plans ------------------------------------------------------------
    @router.post("/plans", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_plan(payload: CreatePlanIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateExecutionPlan(
                episode_id=payload.episode_id,
                episode_revision_id=payload.episode_revision_id,
                scenes=tuple(payload.scenes),
                actions=tuple(payload.actions),
                recording_profile=payload.recording_profile or {},
                payload_bundles=payload.payload_bundles,
                source_workspace_hash=payload.source_workspace_hash,
                preparation_revision=payload.preparation_revision,
                plan_id=payload.plan_id,
                metadata=payload.metadata,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/plans", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_plans(request: Request, episode_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListLiveExecutionPlans(episode_id=episode_id))
        return {"plans": [view.to_payload() for view in views]}

    @router.get("/plans/{plan_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_plan(plan_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetLiveExecutionPlan(plan_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/plans/{plan_id}/content", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def patch_plan_content(plan_id: str, payload: UpdatePlanContentIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdatePlanContent(
                plan_id=plan_id,
                scenes=tuple(payload.scenes) if payload.scenes is not None else None,
                actions=tuple(payload.actions) if payload.actions is not None else None,
                payload_bundles=payload.payload_bundles,
                source_workspace_hash=payload.source_workspace_hash,
                expected_version=payload.expected_version,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_plan(plan_id: str, payload: TransitionPlanIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target=payload.target, expected_version=payload.expected_version, current_episode_revision_id=payload.current_episode_revision_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/prepare", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def prepare_plan(plan_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target="PREPARED"))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/validate", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def validate_plan(plan_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target="VALIDATED"))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/freeze", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def freeze_plan(plan_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target="FROZEN"))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/mark-stale", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def mark_stale(plan_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target="STALE"))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/mark-invalid", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def mark_invalid(plan_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionPlan(plan_id=plan_id, target="INVALID"))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/staleness-check", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def staleness_check(plan_id: str, payload: TransitionPlanIn, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        if payload.current_episode_revision_id is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="current_episode_revision_id is required")
        result = await query_bus.ask(app_queries.StalenessCheck(plan_id=plan_id, current_episode_revision_id=payload.current_episode_revision_id))
        return result  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/privacy-scan", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def privacy_scan(plan_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        result = await query_bus.ask(app_queries.PrivacyScan(plan_id))
        return result  # type: ignore[no-any-return]

    @router.post("/plans/prepare-package", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def prepare_package(payload: PreparePackageIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            PrepareRecordingPackage(
                episode_id=payload.episode_id, episode_revision_id=payload.episode_revision_id, scenes=tuple(payload.scenes), recording_profile=payload.recording_profile, source_workspace_hash=payload.source_workspace_hash, payload=payload.payload
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    # -- action dispatch -------------------------------------------------
    @router.post("/plans/{plan_id}/actions/{action_id}/prepare", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def dispatch_action(plan_id: str, action_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result = await command_bus.dispatch(DispatchPreparedAction(plan_id=plan_id, action_id=action_id))
        return result  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/actions/result", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def record_action_result(plan_id: str, payload: RecordActionResultIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        # Take id must be in payload.observed? but we require it via query? To keep thin, take_id is observed['take_id']?
        # We expose alternative: action result needs take_id; client should send it in observed.
        take_id = payload.observed.get("take_id") or payload.observed.get("takeId") or ""
        if not take_id:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="observed.take_id is required")
        result = await command_bus.dispatch(
            RecordActionResult(
                plan_id=plan_id,
                take_id=take_id,
                action_id=payload.observed.get("action_id") or payload.observed.get("actionId") or "",
                status=payload.status,
                execution_id=payload.execution_id,
                idempotency_key=payload.idempotency_key,
                t=payload.t,
                detail=payload.detail,
                before_hash_observed=payload.before_hash_observed,
                after_hash_observed=payload.after_hash_observed,
                observed=payload.observed,
                scene_id=payload.scene_id,
                cue_id=payload.cue_id,
            )
        )
        # If action_id was in path we override; but use observed action_id if provided else path? Simplify: use path if not in observed
        return result  # type: ignore[no-any-return]

    # -- takes -----------------------------------------------------------
    @router.post("/plans/{plan_id}/takes", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_take(plan_id: str, payload: CreateTakeIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateTake(plan_id=plan_id, episode_id=payload.episode_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/plans/{plan_id}/takes", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_takes(plan_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListTakes(execution_plan_id=plan_id))
        return {"takes": [view.to_payload() for view in views]}

    @router.get("/takes/{take_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_take(take_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetTake(take_id))
        return view.to_payload()  # type: ignore[no-any-return]

    # -- events ----------------------------------------------------------
    @router.post("/takes/{take_id}/events", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def append_event(take_id: str, payload: AppendEventIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            AppendTakeEvent(
                take_id=take_id,
                event_type=payload.event_type,
                t=payload.t,
                scene_id=payload.scene_id,
                cue_id=payload.cue_id,
                action_id=payload.action_id,
                segment_id=payload.segment_id,
                execution_id=payload.execution_id,
                marker_type=payload.marker_type,
                detail=payload.detail,
                payload=payload.payload,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/takes/{take_id}/events", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_events(take_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListTakeEvents(take_id))
        return {"events": [view.to_payload() for view in views]}

    # -- segments --------------------------------------------------------
    @router.post("/takes/{take_id}/segments", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_segment(take_id: str, payload: CreateSegmentIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateSegment(
                take_id=take_id,
                segment_index=payload.segment_index,
                file_token=payload.file_token,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                duration_sec=payload.duration_sec,
                is_playable=payload.is_playable,
                manifest=payload.manifest,
                segment_id=payload.segment_id,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/takes/{take_id}/segments", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_segments(take_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListTakeSegments(take_id))
        return {"segments": [view.to_payload() for view in views]}

    # -- director sessions -----------------------------------------------
    @router.post("/sessions/bootstrap", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def bootstrap_session(payload: BootstrapDirectorSessionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        # execution_plan_id is in payload? For generic bootstrap we require it; episode_id may be optional.
        # We expect payload to carry execution_plan_id via observed? Instead we treat provider bootstrap as needing plan_id.
        # For compatibility, we demand execution_plan_id to be in provider_id? No.
        # Alternative: bootstrap expects plan_id in body as episode_id? Let's interpret: episode_id may be plan_id fallback.
        # Simpler: if payload.episode_id looks like plan id, use it.
        # But we can also accept a generic "execution_plan_id" field alias via episode_id for now.
        # To make contract explicit, we require query param? Let's just error if missing.
        from fastapi import HTTPException

        # Try to get execution_plan_id from request body extension: we check if payload.model_extra contains it
        extra = getattr(payload, "model_extra", None) or {}
        execution_plan_id = extra.get("execution_plan_id") or extra.get("plan_id")
        if not execution_plan_id:
            # fallback: use episode_id as plan_id when it starts with "plan_"
            if payload.episode_id and payload.episode_id.startswith("plan_"):
                execution_plan_id = payload.episode_id
                payload_episode = None
            else:
                raise HTTPException(status_code=422, detail="execution_plan_id is required")
        else:
            payload_episode = payload.episode_id
        result = await command_bus.dispatch(BootstrapDirectorSession(execution_plan_id=execution_plan_id, episode_id=payload_episode, provider_id=payload.provider_id, model_id=payload.model_id, connection_state=payload.connection_state))
        return result  # type: ignore[no-any-return]

    @router.post("/plans/{plan_id}/sessions", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def bootstrap_session_for_plan(plan_id: str, payload: BootstrapDirectorSessionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result = await command_bus.dispatch(BootstrapDirectorSession(execution_plan_id=plan_id, episode_id=payload.episode_id, provider_id=payload.provider_id, model_id=payload.model_id, connection_state=payload.connection_state))
        return result  # type: ignore[no-any-return]

    @router.get("/sessions/{session_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_session(session_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetDirectorSession(session_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/sessions/{session_id}/refresh", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def refresh_session(session_id: str, payload: RefreshDirectorSessionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result = await command_bus.dispatch(RefreshDirectorSession(session_id=session_id, connection_state=payload.connection_state))
        return result  # type: ignore[no-any-return]

    @router.get("/sessions", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_sessions(request: Request, execution_plan_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListDirectorSessions(execution_plan_id=execution_plan_id))
        return {"sessions": [view.to_payload() for view in views]}

    # -- failure classification ------------------------------------------
    @router.post("/failures/classify", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def classify_failure(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        failure = str(payload.get("failure", ""))
        result = await query_bus.ask(app_queries.ClassifyFailure(failure))
        return result  # type: ignore[no-any-return]

    return router
