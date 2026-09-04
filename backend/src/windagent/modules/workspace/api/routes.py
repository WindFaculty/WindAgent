"""HTTP REST routes for the Workspace module (mounted under /api/v4/workspaces)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from windagent.platform.commands import CommandBus
from windagent.platform.queries import QueryBus

from ..application.commands import (
    AcquireWorkspaceLock,
    AddWorkspaceMember,
    ArchiveWorkspace,
    BindProjectToWorkspace,
    CreateWorkspace,
    ReleaseWorkspaceLock,
    RemoveWorkspaceMember,
    RestoreWorkspace,
    UnbindProjectFromWorkspace,
    UpdateWorkspace,
)
from ..application.queries import (
    GetWorkspace,
    GetWorkspaceBySlug,
    GetWorkspaceMembers,
    GetWorkspaceSnapshot,
    ListWorkspaceLocks,
    ListWorkspaces,
    ValidateWorkspacePath,
)
from ..application.runtime import WorkspaceServices, bind_services
from ..domain.errors import (
    InvalidWorkspaceStateTransitionError,
    WorkspaceAccessDeniedError,
    WorkspaceError,
    WorkspaceLockConflictError,
    WorkspaceNotFoundError,
    WorkspacePathViolationError,
    WorkspaceQuotaExceededError,
    WorkspaceSlugAlreadyExistsError,
    WorkspaceStaleVersionError,
)

MODULE_ID = "workspace"
MODULE_VERSION = "1.0.0"
WORKSPACES_PREFIX = "/workspaces"


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #


async def _runtime_services(request: Request) -> AsyncIterator[Any]:
    override = getattr(request.app.state, "workspace_services_override", None)
    if override is not None:
        with bind_services(override):
            yield override
        return

    db = getattr(request.app.state, "database", None)
    if db is None:
        from ..infrastructure.memory import create_in_memory_scope_factory

        _, scope_factory = create_in_memory_scope_factory()
        services = WorkspaceServices(transaction_factory=scope_factory)
    else:
        from ..infrastructure.repository import sql_scope_factory

        services = WorkspaceServices(transaction_factory=sql_scope_factory(db))

    with bind_services(services):
        yield services



# --------------------------------------------------------------------------- #
# Request DTOs
# --------------------------------------------------------------------------- #


class CreateWorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)
    root_path: str = Field(default="", max_length=500)
    owner_id: str = Field(default="system", max_length=100)
    workspace_id: str | None = Field(default=None, max_length=36)
    description: str = Field(default="", max_length=2000)
    tier: str = Field(default="LOCAL")
    quota: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class UpdateWorkspaceIn(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] | None = None


class VersionedActionIn(BaseModel):
    expected_version: int = Field(ge=1)


class AddMemberIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    role: str = Field(default="MEMBER")
    actor_id: str = Field(default="system", max_length=100)


class AcquireLockIn(BaseModel):
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=200)
    holder_id: str = Field(min_length=1, max_length=100)
    ttl_seconds: int | None = Field(default=None, ge=1)


class UpdateQuotaIn(BaseModel):
    max_projects: int | None = Field(default=None, ge=1)
    max_storage_bytes: int | None = Field(default=None, ge=1)
    max_concurrent_runs: int | None = Field(default=None, ge=1)
    max_credits_per_month: float | None = Field(default=None, ge=0.0)


class UpdatePolicyIn(BaseModel):
    allowed_runtimes: list[str] | None = None
    sandbox_mode: bool | None = None
    require_approvals: bool | None = None
    allow_shell: bool | None = None
    allow_network: bool | None = None


class ValidatePathIn(BaseModel):
    target_path: str = Field(min_length=1, max_length=500)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_buses(request: Request) -> tuple[CommandBus, QueryBus]:
    cmd_bus = getattr(request.app.state, "command_bus", None)
    query_bus = getattr(request.app.state, "query_bus", None)
    if cmd_bus is None or query_bus is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CommandBus or QueryBus not available on app state",
        )
    return cmd_bus, query_bus


def _handle_domain_error(exc: Exception) -> None:
    if isinstance(exc, WorkspaceNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceSlugAlreadyExistsError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceStaleVersionError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceLockConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceAccessDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceQuotaExceededError):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    if isinstance(exc, (WorkspacePathViolationError, InvalidWorkspaceStateTransitionError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


# --------------------------------------------------------------------------- #
# Router factory
# --------------------------------------------------------------------------- #


def create_workspace_router() -> APIRouter:
    router = APIRouter(
        prefix=WORKSPACES_PREFIX,
        tags=["workspaces"],
        dependencies=[Depends(_runtime_services)],
    )

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_workspace(body: CreateWorkspaceIn, request: Request) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = CreateWorkspace(
            name=body.name,
            slug=body.slug,
            root_path=body.root_path or f"/workspaces/{body.slug}",
            owner_id=body.owner_id,
            workspace_id=body.workspace_id,
            description=body.description,
            tier=body.tier,
            quota=body.quota,
            policy=body.policy,
            metadata=body.metadata,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("")
    async def list_workspaces(
        request: Request,
        owner_id: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        q = ListWorkspaces(owner_id=owner_id, status=status_filter, limit=limit, offset=offset)
        views = await query_bus.ask(q)
        return [v.to_payload() for v in views]

    @router.get("/{id_or_slug}")
    async def get_workspace(id_or_slug: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        # Try by ID first, then by slug
        view = await query_bus.ask(GetWorkspace(workspace_id=id_or_slug))
        if view is None:
            view = await query_bus.ask(GetWorkspaceBySlug(slug=id_or_slug))
        if view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace not found: {id_or_slug}",
            )
        return view.to_payload()

    @router.patch("/{workspace_id}")
    async def update_workspace(
        workspace_id: str, body: UpdateWorkspaceIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = UpdateWorkspace(
            workspace_id=workspace_id,
            expected_version=body.expected_version,
            name=body.name,
            description=body.description,
            metadata=body.metadata,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/{workspace_id}/archive")
    async def archive_workspace(
        workspace_id: str, body: VersionedActionIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            view = await cmd_bus.dispatch(
                ArchiveWorkspace(workspace_id=workspace_id, expected_version=body.expected_version)
            )
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/{workspace_id}/restore")
    async def restore_workspace(
        workspace_id: str, body: VersionedActionIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            view = await cmd_bus.dispatch(
                RestoreWorkspace(workspace_id=workspace_id, expected_version=body.expected_version)
            )
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
    async def add_member(
        workspace_id: str, body: AddMemberIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            member = await cmd_bus.dispatch(
                AddWorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=body.user_id,
                    role=body.role,
                    actor_id=body.actor_id,
                )
            )
            return member.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/{workspace_id}/members")
    async def get_members(workspace_id: str, request: Request) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        try:
            members = await query_bus.ask(GetWorkspaceMembers(workspace_id=workspace_id))
            return [m.to_payload() for m in members]
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.delete("/{workspace_id}/members/{user_id}")
    async def remove_member(
        workspace_id: str,
        user_id: str,
        request: Request,
        actor_id: str = Query(default="system"),
    ) -> dict[str, bool]:
        cmd_bus, _ = _get_buses(request)
        try:
            ok = await cmd_bus.dispatch(
                RemoveWorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    actor_id=actor_id,
                )
            )
            return {"removed": ok}
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/{workspace_id}/projects/{project_id}")
    async def bind_project(
        workspace_id: str, project_id: str, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            view = await cmd_bus.dispatch(
                BindProjectToWorkspace(workspace_id=workspace_id, project_id=project_id)
            )
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.delete("/{workspace_id}/projects/{project_id}")
    async def unbind_project(
        workspace_id: str, project_id: str, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            view = await cmd_bus.dispatch(
                UnbindProjectFromWorkspace(workspace_id=workspace_id, project_id=project_id)
            )
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/{workspace_id}/locks", status_code=status.HTTP_201_CREATED)
    async def acquire_lock(
        workspace_id: str, body: AcquireLockIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            lock = await cmd_bus.dispatch(
                AcquireWorkspaceLock(
                    workspace_id=workspace_id,
                    resource_type=body.resource_type,
                    resource_id=body.resource_id,
                    holder_id=body.holder_id,
                    ttl_seconds=body.ttl_seconds,
                )
            )
            return lock.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/{workspace_id}/locks")
    async def list_locks(workspace_id: str, request: Request) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        try:
            locks = await query_bus.ask(ListWorkspaceLocks(workspace_id=workspace_id))
            return [item.to_payload() for item in locks]
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.delete("/{workspace_id}/locks/{resource_id}")
    async def release_lock(
        workspace_id: str,
        resource_id: str,
        request: Request,
        holder_id: str = Query(default="system"),
    ) -> dict[str, bool]:
        cmd_bus, _ = _get_buses(request)
        try:
            ok = await cmd_bus.dispatch(
                ReleaseWorkspaceLock(
                    workspace_id=workspace_id,
                    resource_id=resource_id,
                    holder_id=holder_id,
                )
            )
            return {"released": ok}
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/{workspace_id}/snapshot")
    async def get_snapshot(workspace_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        snap = await query_bus.ask(GetWorkspaceSnapshot(workspace_id=workspace_id))
        if snap is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Snapshot not found for workspace {workspace_id}",
            )
        return snap.to_payload()

    @router.post("/{workspace_id}/validate-path")
    async def validate_path(
        workspace_id: str, body: ValidatePathIn, request: Request
    ) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        res = await query_bus.ask(
            ValidateWorkspacePath(workspace_id=workspace_id, target_path=body.target_path)
        )
        return res.to_payload()

    return router


CreateWorkspaceIn.model_rebuild()
UpdateWorkspaceIn.model_rebuild()
VersionedActionIn.model_rebuild()
AddMemberIn.model_rebuild()
AcquireLockIn.model_rebuild()
UpdateQuotaIn.model_rebuild()
UpdatePolicyIn.model_rebuild()
ValidatePathIn.model_rebuild()

