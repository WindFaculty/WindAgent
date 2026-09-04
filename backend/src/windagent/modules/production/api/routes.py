"""HTTP surface of Production (mounted under ``/api/v4``)."""

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
    CreateAssetRevision,
    CreateAudioTrack,
    CreateCodeVideoProject,
    CreateEdl,
    CreateMixPlan,
    CreateProductionAsset,
    CreateProductionProject,
    CreateProductionRevision,
    CreateRenderJob,
    DeriveProductionRevision,
    LockProductionRevision,
    TransitionCodeVideoProject,
    TransitionProductionAsset,
    TransitionRenderJob,
    UpdateEdl,
    UpdateProductionProject,
)
from ..application.runtime import ProductionServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "production"
MODULE_VERSION = "1.0.0"
PRODUCTION_PREFIX = "/production"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "production.read"
WRITE_ACTION = "production.write"
RESOURCE_TYPE = "production"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class CreateProductionProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=2000)
    owner_id: str = Field(default="system", max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateProductionProjectIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class CreateProductionRevisionIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    content_hash: str = Field(min_length=64, max_length=64)
    creator: str = Field(default="system", max_length=200)
    actor: str | None = Field(default=None, max_length=200)
    parent_revision_id: str | None = Field(default=None, max_length=36)
    summary: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeriveProductionRevisionIn(BaseModel):
    new_content_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(default="system", max_length=200)
    invalidation_intent: str | None = Field(default=None, max_length=40)
    summary: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=0)


class LockProductionRevisionIn(BaseModel):
    expected_content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    expected_version: int | None = Field(default=None, ge=0)


class CreateProductionAssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=400)
    kind: str = Field(default="OTHER", max_length=50)
    project_id: str | None = Field(default=None, max_length=36)
    description: str = Field(default="", max_length=2000)
    source_type: str = Field(default="UPLOADED", max_length=30)
    license_state: str = Field(default="UNKNOWN", max_length=30)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionProductionAssetIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)
    new_review_record: bool = Field(default=False)


class CreateAssetRevisionIn(BaseModel):
    asset_id: str = Field(min_length=1, max_length=36)
    content_hash: str = Field(min_length=64, max_length=64)
    media_type: str = Field(default="IMAGE", max_length=30)
    mime_type: str = Field(default="image/png", max_length=100)
    size_bytes: int = Field(default=0, ge=0)
    supersedes_revision_id: str | None = Field(default=None, max_length=36)
    normalized_format: str | None = Field(default=None, max_length=50)
    preview_artifacts: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class CreateAudioTrackIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=400)
    kind: str = Field(default="DIALOGUE", max_length=20)
    character_id: str | None = Field(default=None, max_length=100)
    dialogue_text: str = Field(default="", max_length=5000)
    source_path: str = Field(default="", max_length=500)
    source_hash: str = Field(default="", max_length=64)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    channels: int = Field(default=1, ge=1, le=8)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    language: str = Field(default="en", max_length=20)
    voice_profile_id: str | None = Field(default=None, max_length=100)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateMixPlanIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    title: str = Field(default="main", max_length=400)
    loudness_target_lufs: float = Field(default=-16.0)
    peak_ceiling_db: float = Field(default=-1.0)
    policy_version: str = Field(default="loudness-v1", max_length=50)
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCodeVideoProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=2000)
    repo_url: str = Field(default="", max_length=500)
    branch: str = Field(default="main", max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionCodeVideoProjectIn(BaseModel):
    target_status: str = Field(min_length=1, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)


class CreateRenderJobIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    scene_id: str = Field(default="", max_length=100)
    shot_id: str = Field(default="", max_length=100)
    revision_id: str | None = Field(default=None, max_length=36)
    frame_start: int = Field(default=1, ge=1)
    frame_end: int = Field(default=24, ge=1)
    colorspace: str = Field(default="sRGB", max_length=50)
    profile_id: str = Field(default="main_1080p_h264", max_length=100)
    input_hash: str = Field(default="", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionRenderJobIn(BaseModel):
    target_status: str = Field(min_length=1, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)
    output_hash: str | None = Field(default=None, max_length=64)
    error: str | None = Field(default=None, max_length=1000)


class CreateEdlIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    revision_id: str = Field(min_length=1, max_length=36)
    title: str = Field(default="main", max_length=400)
    items: list[dict[str, Any]] = Field(default_factory=list)
    audio_mix_plan_id: str = Field(default="", max_length=36)
    subtitle_track_id: str | None = Field(default=None, max_length=100)
    encoding_profile: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateEdlIn(BaseModel):
    title: str | None = Field(default=None, max_length=400)
    status: str | None = Field(default=None, max_length=20)
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Policy + ambient services scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_production_policy(action: str, resource_type: str = RESOURCE_TYPE) -> Callable[[Request], Awaitable[PolicyDecision]]:
    normalized_action = action

    async def dependency(request: Request) -> PolicyDecision:
        engine = getattr(request.app.state, "policy_engine", None)
        if engine is None:
            return PolicyDecision(effect=PolicyEffect.ALLOW, reason="no policy engine is configured", policy_id=POLICY_UNCONFIGURED_POLICY_ID)
        decision = await cast(PolicyEngine, engine).decide(
            PolicyRequest(action=normalized_action, resource_type=resource_type, actor_id=_principal_actor_id(request))  # type: ignore[arg-type]
        )
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


def services_from_state(request: Request) -> ProductionServices:
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="production requires a configured database")
    from windagent.platform.security import EnvironmentSecretStore

    return ProductionServices(scope_factory=sql_scope_factory(database), secrets=cast(SecretStore, EnvironmentSecretStore()), telemetry=getattr(request.app.state, "telemetry", None))


async def services_scope(request: Request) -> AsyncIterator[None]:
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_production_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_production_policy(WRITE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    return request.app.state.command_bus, request.app.state.query_bus


def create_production_router() -> APIRouter:
    router = APIRouter(prefix=PRODUCTION_PREFIX, tags=["production"])

    # -- projects ----------------------------------------------------------
    @router.post("/projects", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_project(payload: CreateProductionProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateProductionProject(title=payload.title, description=payload.description, owner_id=payload.owner_id, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/projects", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_projects(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListProductionProjects())
        return {"projects": [view.to_payload() for view in views]}

    @router.get("/projects/{project_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_project(project_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetProductionProject(project_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/projects/{project_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_project(project_id: str, payload: UpdateProductionProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateProductionProject(project_id=project_id, title=payload.title, description=payload.description, status=payload.status, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    # -- revisions ---------------------------------------------------------
    @router.post("/revisions", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_revision(payload: CreateProductionRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateProductionRevision(project_id=payload.project_id, content_hash=payload.content_hash, creator=payload.creator, actor=payload.actor, parent_revision_id=payload.parent_revision_id, summary=payload.summary, metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/revisions/{parent_revision_id}/derive", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def derive_revision(parent_revision_id: str, payload: DeriveProductionRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        _, query_bus = _buses(request)
        parent = await query_bus.ask(app_queries.GetProductionRevision(parent_revision_id))
        view = await command_bus.dispatch(
            DeriveProductionRevision(project_id=parent.project_id, parent_revision_id=parent_revision_id, new_content_hash=payload.new_content_hash, actor=payload.actor, invalidation_intent=payload.invalidation_intent, summary=payload.summary, expected_version=payload.expected_version)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/revisions/{revision_id}/lock", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def lock_revision(revision_id: str, payload: LockProductionRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(LockProductionRevision(revision_id=revision_id, expected_content_hash=payload.expected_content_hash, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/revisions/{revision_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_revision(revision_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetProductionRevision(revision_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/revisions", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_revisions(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListProductionRevisions(project_id=project_id))
        return {"revisions": [view.to_payload() for view in views]}

    # -- assets ------------------------------------------------------------
    @router.post("/assets", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_asset(payload: CreateProductionAssetIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateProductionAsset(name=payload.name, kind=payload.kind, project_id=payload.project_id, description=payload.description, source_type=payload.source_type, license_state=payload.license_state, tags=tuple(payload.tags), metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/assets/{asset_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_asset(asset_id: str, payload: TransitionProductionAssetIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionProductionAsset(asset_id=asset_id, target_state=payload.target_state, expected_version=payload.expected_version, new_review_record=payload.new_review_record))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/assets/{asset_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_asset(asset_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetProductionAsset(asset_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/assets", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_assets(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListProductionAssets(project_id=project_id))
        return {"assets": [view.to_payload() for view in views]}

    @router.post("/asset-revisions", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_asset_revision(payload: CreateAssetRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateAssetRevision(asset_id=payload.asset_id, content_hash=payload.content_hash, media_type=payload.media_type, mime_type=payload.mime_type, size_bytes=payload.size_bytes, supersedes_revision_id=payload.supersedes_revision_id, normalized_format=payload.normalized_format, preview_artifacts=payload.preview_artifacts, validation_report=payload.validation_report, provenance=payload.provenance)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/asset-revisions/{revision_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_asset_revision(revision_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetAssetRevision(revision_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/asset-revisions", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_asset_revisions(request: Request, asset_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListAssetRevisions(asset_id=asset_id))
        return {"revisions": [view.to_payload() for view in views]}

    # -- audio -------------------------------------------------------------
    @router.post("/audio/tracks", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_audio_track(payload: CreateAudioTrackIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateAudioTrack(project_id=payload.project_id, title=payload.title, kind=payload.kind, character_id=payload.character_id, dialogue_text=payload.dialogue_text, source_path=payload.source_path, source_hash=payload.source_hash, sample_rate=payload.sample_rate, channels=payload.channels, duration_seconds=payload.duration_seconds, language=payload.language, voice_profile_id=payload.voice_profile_id, provenance=payload.provenance, metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/audio/tracks/{track_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_audio_track(track_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetAudioTrack(track_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/audio/tracks", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_audio_tracks(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListAudioTracks(project_id=project_id))
        return {"tracks": [view.to_payload() for view in views]}

    @router.post("/audio/mix-plans", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_mix_plan(payload: CreateMixPlanIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateMixPlan(project_id=payload.project_id, title=payload.title, loudness_target_lufs=payload.loudness_target_lufs, peak_ceiling_db=payload.peak_ceiling_db, policy_version=payload.policy_version, tracks=tuple(payload.tracks), metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/audio/mix-plans/{mix_plan_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_mix_plan(mix_plan_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetMixPlan(mix_plan_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/audio/mix-plans", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_mix_plans(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListMixPlans(project_id=project_id))
        return {"mix_plans": [view.to_payload() for view in views]}

    # -- code video --------------------------------------------------------
    @router.post("/code-video/projects", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_code_video_project(payload: CreateCodeVideoProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateCodeVideoProject(title=payload.title, description=payload.description, repo_url=payload.repo_url, branch=payload.branch, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/code-video/projects/{project_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_code_video_project(project_id: str, payload: TransitionCodeVideoProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionCodeVideoProject(project_id=project_id, target_status=payload.target_status, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/code-video/projects/{project_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_code_video_project(project_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetCodeVideoProject(project_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/code-video/projects", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_code_video_projects(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListCodeVideoProjects())
        return {"projects": [view.to_payload() for view in views]}

    # -- rendering ---------------------------------------------------------
    @router.post("/render/jobs", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_render_job(payload: CreateRenderJobIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateRenderJob(project_id=payload.project_id, scene_id=payload.scene_id, shot_id=payload.shot_id, revision_id=payload.revision_id, frame_start=payload.frame_start, frame_end=payload.frame_end, colorspace=payload.colorspace, profile_id=payload.profile_id, input_hash=payload.input_hash, metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/render/jobs/{job_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_render_job(job_id: str, payload: TransitionRenderJobIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionRenderJob(job_id=job_id, target_status=payload.target_status, expected_version=payload.expected_version, output_hash=payload.output_hash, error=payload.error))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/render/jobs/{job_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_render_job(job_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetRenderJob(job_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/render/jobs", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_render_jobs(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListRenderJobs(project_id=project_id))
        return {"jobs": [view.to_payload() for view in views]}

    # -- edl / postproduction ----------------------------------------------
    @router.post("/edls", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_edl(payload: CreateEdlIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateEdl(project_id=payload.project_id, revision_id=payload.revision_id, title=payload.title, items=tuple(payload.items), audio_mix_plan_id=payload.audio_mix_plan_id, subtitle_track_id=payload.subtitle_track_id, encoding_profile=payload.encoding_profile, metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/edls/{edl_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_edl(edl_id: str, payload: UpdateEdlIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(UpdateEdl(edl_id=edl_id, title=payload.title, status=payload.status, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/edls/{edl_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_edl(edl_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetEdl(edl_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/edls", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_edls(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListEdls(project_id=project_id))
        return {"edls": [view.to_payload() for view in views]}

    return router
