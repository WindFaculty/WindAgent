"""HTTP surface of Studio (mounted under ``/api/v4``).

Routes stay thin per plan section 12: validate DTO, dispatch through
Command/Query buses, map to response payload.  Every mutating route is
policy-gated, and handlers resolve services through the ambient scope.
"""

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
    CreateArtifact,
    CreateCharacter,
    CreateEpisode,
    CreateProject,
    CreateRevision,
    CreateSeries,
    CreateStoryboard,
    DeriveRevision,
    LockRevision,
    ReorderStoryboard,
    TransitionEpisode,
    UpdateCharacter,
    UpdateEpisode,
    UpdateProject,
    UpdateSeries,
    UpdateStoryboard,
    UpsertWorldLocation,
    UpsertWorldProp,
)
from ..application.handlers import StoryGenerateJobHandler  # noqa: F401
from ..application.runtime import StudioServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "studio"
MODULE_VERSION = "1.0.0"
STUDIO_PREFIX = "/studio"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "studio.read"
WRITE_ACTION = "studio.write"
DELETE_ACTION = "studio.delete"
RESOURCE_TYPE = "studio"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class CreateProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    owner_id: str = Field(default="system", max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateProjectIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class CreateSeriesIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    project_id: str | None = Field(default=None, max_length=36)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSeriesIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class CreateEpisodeIn(BaseModel):
    series_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=400)
    episode_number: int = Field(default=1, ge=1)
    logline: str = Field(default="", max_length=2000)
    project_id: str | None = Field(default=None, max_length=36)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateEpisodeIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    logline: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class TransitionEpisodeIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=50)
    expected_version: int | None = Field(default=None, ge=0)


class CreateRevisionIn(BaseModel):
    series_id: str = Field(min_length=1, max_length=36)
    episode_id: str = Field(min_length=1, max_length=36)
    content_hash: str = Field(min_length=64, max_length=64)
    creator: str = Field(default="system", max_length=200)
    actor: str | None = Field(default=None, max_length=200)
    parent_revision_id: str | None = Field(default=None, max_length=36)
    summary: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeriveRevisionIn(BaseModel):
    series_id: str = Field(min_length=1, max_length=36)
    new_content_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(default="system", max_length=200)
    invalidation_intent: str | None = Field(default=None, max_length=20)
    summary: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=0)


class LockRevisionIn(BaseModel):
    expected_content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    expected_version: int | None = Field(default=None, ge=0)


class CreateArtifactIn(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=100)
    series_id: str = Field(min_length=1, max_length=36)
    episode_id: str = Field(min_length=1, max_length=36)
    content: Any = Field(default_factory=dict)
    revision_id: str | None = Field(default=None, max_length=36)
    input_artifact_refs: list[str] = Field(default_factory=list)
    created_by: str = Field(default="system", max_length=200)
    extra: dict[str, Any] = Field(default_factory=dict)


class CreateCharacterIn(BaseModel):
    series_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=300)
    display_name: str = Field(default="", max_length=300)
    role: str = Field(default="supporting", max_length=50)
    archetype: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=5000)
    traits: list[str] = Field(default_factory=list)
    backstory: str = Field(default="", max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateCharacterIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    traits: list[str] | None = None
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class WorldLocationIn(BaseModel):
    location_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    geography: str = Field(default="", max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorldPropIn(BaseModel):
    prop_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    significance: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateStoryboardIn(BaseModel):
    episode_id: str = Field(min_length=1, max_length=36)
    series_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=400)
    panels: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateStoryboardIn(BaseModel):
    panels: list[dict[str, Any]] | None = None
    expected_version: int | None = Field(default=None, ge=0)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)


class ReorderStoryboardIn(BaseModel):
    panel_ids: list[str] = Field(min_length=1)
    expected_version: int | None = Field(default=None, ge=0)


# --------------------------------------------------------------------------- #
# Policy + ambient services scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_studio_policy(
    action: str, resource_type: str = RESOURCE_TYPE
) -> Callable[[Request], Awaitable[PolicyDecision]]:
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


def services_from_state(request: Request) -> StudioServices:
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="studio requires a configured database")
    from windagent.platform.security import EnvironmentSecretStore

    return StudioServices(scope_factory=sql_scope_factory(database), secrets=cast(SecretStore, EnvironmentSecretStore()), telemetry=getattr(request.app.state, "telemetry", None))


async def services_scope(request: Request) -> AsyncIterator[None]:
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_studio_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_studio_policy(WRITE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    return request.app.state.command_bus, request.app.state.query_bus


def create_studio_router() -> APIRouter:
    router = APIRouter(prefix=STUDIO_PREFIX, tags=["studio"])

    # -- projects ----------------------------------------------------------
    @router.post("/projects", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_project(payload: CreateProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateProject(title=payload.title, description=payload.description, owner_id=payload.owner_id, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/projects", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_projects(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListProjects())
        return {"projects": [view.to_payload() for view in views]}

    @router.get("/projects/{project_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_project(project_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetProject(project_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/projects/{project_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_project(project_id: str, payload: UpdateProjectIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateProject(project_id=project_id, title=payload.title, description=payload.description, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    # -- series ------------------------------------------------------------
    @router.post("/series", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_series(payload: CreateSeriesIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateSeries(title=payload.title, description=payload.description, project_id=payload.project_id, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/series", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_series(request: Request, project_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListSeries(project_id=project_id))
        return {"series": [view.to_payload() for view in views]}

    @router.get("/series/{series_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_series(series_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetSeries(series_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/series/{series_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_series(series_id: str, payload: UpdateSeriesIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(UpdateSeries(series_id=series_id, title=payload.title, description=payload.description, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch))
        return view.to_payload()  # type: ignore[no-any-return]

    # -- episodes ----------------------------------------------------------
    @router.post("/episodes", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_episode(payload: CreateEpisodeIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateEpisode(series_id=payload.series_id, title=payload.title, episode_number=payload.episode_number, logline=payload.logline, project_id=payload.project_id, metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/episodes", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_episodes(request: Request, series_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListEpisodes(series_id=series_id))
        return {"episodes": [view.to_payload() for view in views]}

    @router.get("/episodes/{episode_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_episode(episode_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetEpisode(episode_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/episodes/{episode_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_episode(episode_id: str, payload: UpdateEpisodeIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateEpisode(episode_id=episode_id, title=payload.title, logline=payload.logline, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/episodes/{episode_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_episode(episode_id: str, payload: TransitionEpisodeIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionEpisode(episode_id=episode_id, target_state=payload.target_state, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    # -- revisions ---------------------------------------------------------
    @router.post("/revisions", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_revision(payload: CreateRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateRevision(
                series_id=payload.series_id,
                episode_id=payload.episode_id,
                content_hash=payload.content_hash,
                creator=payload.creator,
                actor=payload.actor,
                parent_revision_id=payload.parent_revision_id,
                summary=payload.summary,
                metadata=payload.metadata,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/revisions/{parent_revision_id}/derive", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def derive_revision(parent_revision_id: str, payload: DeriveRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        # Need episode_id from parent? Derive command aggregates episode/series so we fetch parent first?
        # Client supplies series_id again; we also load parent to infer episode.
        _, query_bus = _buses(request)
        parent = await query_bus.ask(app_queries.GetRevision(parent_revision_id))
        view = await command_bus.dispatch(
            DeriveRevision(
                episode_id=parent.episode_id,
                series_id=payload.series_id,
                parent_revision_id=parent_revision_id,
                new_content_hash=payload.new_content_hash,
                actor=payload.actor,
                invalidation_intent=payload.invalidation_intent,
                summary=payload.summary,
                expected_version=payload.expected_version,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/revisions/{revision_id}/lock", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def lock_revision(revision_id: str, payload: LockRevisionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(LockRevision(revision_id=revision_id, expected_content_hash=payload.expected_content_hash, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/revisions/{revision_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_revision(revision_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetRevision(revision_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/revisions", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_revisions(request: Request, episode_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListRevisions(episode_id=episode_id))
        return {"revisions": [view.to_payload() for view in views]}

    # -- artifacts ---------------------------------------------------------
    @router.post("/artifacts", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_artifact(payload: CreateArtifactIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateArtifact(
                artifact_type=payload.artifact_type,
                series_id=payload.series_id,
                episode_id=payload.episode_id,
                content=payload.content,
                revision_id=payload.revision_id,
                input_artifact_refs=tuple(payload.input_artifact_refs),
                created_by=payload.created_by,
                extra=payload.extra,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/artifacts/{artifact_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_artifact(artifact_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetArtifact(artifact_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/artifacts", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_artifacts(
        request: Request,
        episode_id: str | None = QueryParam(default=None),
        artifact_type: str | None = QueryParam(default=None),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListArtifacts(episode_id=episode_id, artifact_type=artifact_type))
        return {"artifacts": [view.to_payload() for view in views]}

    # -- characters --------------------------------------------------------
    @router.post("/characters", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_character(payload: CreateCharacterIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateCharacter(
                series_id=payload.series_id,
                name=payload.name,
                display_name=payload.display_name,
                role=payload.role,
                archetype=payload.archetype,
                description=payload.description,
                traits=tuple(payload.traits),
                backstory=payload.backstory,
                metadata=payload.metadata,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/characters/{character_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_character(character_id: str, payload: UpdateCharacterIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateCharacter(
                character_id=character_id,
                display_name=payload.display_name,
                description=payload.description,
                traits=tuple(payload.traits) if payload.traits is not None else None,
                expected_version=payload.expected_version,
                metadata_patch=payload.metadata_patch,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/characters/{character_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_character(character_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetCharacter(character_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/characters", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_characters(request: Request, series_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListCharacters(series_id=series_id))
        return {"characters": [view.to_payload() for view in views]}

    # -- world -------------------------------------------------------------
    @router.put("/series/{series_id}/world/locations/{location_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def upsert_location(series_id: str, location_id: str, payload: WorldLocationIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result = await command_bus.dispatch(
            UpsertWorldLocation(series_id=series_id, location_id=location_id, name=payload.name, description=payload.description, geography=payload.geography, metadata=payload.metadata)
        )
        return result  # type: ignore[no-any-return]

    @router.get("/series/{series_id}/world/locations", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_locations(series_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        rows = await query_bus.ask(app_queries.ListWorldLocations(series_id=series_id))
        return {"locations": list(rows)}

    @router.put("/series/{series_id}/world/props/{prop_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def upsert_prop(series_id: str, prop_id: str, payload: WorldPropIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result = await command_bus.dispatch(
            UpsertWorldProp(series_id=series_id, prop_id=prop_id, name=payload.name, description=payload.description, significance=payload.significance, metadata=payload.metadata)
        )
        return result  # type: ignore[no-any-return]

    @router.get("/series/{series_id}/world/props", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_props(series_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        rows = await query_bus.ask(app_queries.ListWorldProps(series_id=series_id))
        return {"props": list(rows)}

    # -- storyboard --------------------------------------------------------
    @router.post("/storyboards", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_storyboard(payload: CreateStoryboardIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateStoryboard(episode_id=payload.episode_id, series_id=payload.series_id, title=payload.title, panels=tuple(payload.panels), metadata=payload.metadata)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/storyboards/{storyboard_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_storyboard(storyboard_id: str, payload: UpdateStoryboardIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateStoryboard(storyboard_id=storyboard_id, panels=tuple(payload.panels) if payload.panels is not None else None, expected_version=payload.expected_version, metadata_patch=payload.metadata_patch)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/storyboards/{storyboard_id}/reorder", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def reorder_storyboard(storyboard_id: str, payload: ReorderStoryboardIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(ReorderStoryboard(storyboard_id=storyboard_id, panel_ids=tuple(payload.panel_ids), expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/storyboards/{storyboard_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_storyboard(storyboard_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetStoryboard(storyboard_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/storyboards", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_storyboards(request: Request, episode_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListStoryboards(episode_id=episode_id))
        return {"storyboards": [view.to_payload() for view in views]}

    return router