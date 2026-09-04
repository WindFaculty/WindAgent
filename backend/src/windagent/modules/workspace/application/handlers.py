"""Command, query, and job handlers for Workspace."""

from typing import Any

from .commands import (
    AcquireWorkspaceLock,
    AddWorkspaceMember,
    ArchiveWorkspace,
    BindProjectToWorkspace,
    CreateWorkspace,
    CreateWorkspaceSnapshot,
    RecalculateWorkspaceQuota,
    ReleaseWorkspaceLock,
    RemoveWorkspaceMember,
    RestoreWorkspace,
    SuspendWorkspace,
    UnbindProjectFromWorkspace,
    UpdateWorkspace,
    UpdateWorkspacePolicy,
    UpdateWorkspaceQuota,
)
from .models import (
    PathValidationView,
    WorkspaceLockView,
    WorkspaceMemberView,
    WorkspaceSnapshotView,
    WorkspaceView,
)
from .queries import (
    CheckWorkspaceAccess,
    GetWorkspace,
    GetWorkspaceBySlug,
    GetWorkspaceMembers,
    GetWorkspaceSnapshot,
    ListWorkspaceLocks,
    ListWorkspaces,
    ValidateWorkspacePath,
)
from .runtime import WorkspaceServices, container_for

# --------------------------------------------------------------------------- #
# Command Handlers
# --------------------------------------------------------------------------- #


class CreateWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: CreateWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.create_workspace(command)


class UpdateWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: UpdateWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.update_workspace(command)


class ArchiveWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: ArchiveWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.archive_workspace(command)


class SuspendWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: SuspendWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.suspend_workspace(command)


class RestoreWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: RestoreWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.restore_workspace(command)


class AddWorkspaceMemberHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: AddWorkspaceMember) -> WorkspaceMemberView:
        return await container_for(self._services).workspace.add_member(command)


class RemoveWorkspaceMemberHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: RemoveWorkspaceMember) -> bool:
        return await container_for(self._services).workspace.remove_member(command)


class BindProjectToWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: BindProjectToWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.bind_project(command)


class UnbindProjectFromWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: UnbindProjectFromWorkspace) -> WorkspaceView:
        return await container_for(self._services).workspace.unbind_project(command)


class AcquireWorkspaceLockHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: AcquireWorkspaceLock) -> WorkspaceLockView:
        return await container_for(self._services).workspace.acquire_lock(command)


class ReleaseWorkspaceLockHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: ReleaseWorkspaceLock) -> bool:
        return await container_for(self._services).workspace.release_lock(command)


class UpdateWorkspaceQuotaHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: UpdateWorkspaceQuota) -> WorkspaceView:
        return await container_for(self._services).workspace.update_quota(command)


class UpdateWorkspacePolicyHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: UpdateWorkspacePolicy) -> WorkspaceView:
        return await container_for(self._services).workspace.update_policy(command)


class CreateWorkspaceSnapshotHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: CreateWorkspaceSnapshot) -> WorkspaceSnapshotView:
        return await container_for(self._services).workspace.create_snapshot(command)


class RecalculateWorkspaceQuotaHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, command: RecalculateWorkspaceQuota) -> WorkspaceView:
        return await container_for(self._services).workspace.recalculate_quota(command)


# --------------------------------------------------------------------------- #
# Query Handlers
# --------------------------------------------------------------------------- #


class GetWorkspaceHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetWorkspace) -> WorkspaceView | None:
        return await container_for(self._services).workspace.get_workspace(query)


class GetWorkspaceBySlugHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetWorkspaceBySlug) -> WorkspaceView | None:
        return await container_for(self._services).workspace.get_workspace_by_slug(query)


class ListWorkspacesHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListWorkspaces) -> list[WorkspaceView]:
        return await container_for(self._services).workspace.list_workspaces(query)


class GetWorkspaceMembersHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetWorkspaceMembers) -> list[WorkspaceMemberView]:
        return await container_for(self._services).workspace.get_members(query)


class GetWorkspaceSnapshotHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetWorkspaceSnapshot) -> WorkspaceSnapshotView | None:
        return await container_for(self._services).workspace.get_snapshot(query)


class ListWorkspaceLocksHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListWorkspaceLocks) -> list[WorkspaceLockView]:
        return await container_for(self._services).workspace.list_locks(query)


class ValidateWorkspacePathHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ValidateWorkspacePath) -> PathValidationView:
        return await container_for(self._services).workspace.validate_path(query)


class CheckWorkspaceAccessHandler:
    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, query: CheckWorkspaceAccess) -> bool:
        return await container_for(self._services).workspace.check_access(query)


# --------------------------------------------------------------------------- #
# Job Handlers
# --------------------------------------------------------------------------- #


class WorkspaceQuotaRecalculateJobHandler:
    job_type = "workspace.quota.recalculate"

    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace_id = str(payload.get("workspace_id", ""))
        if not workspace_id:
            return {"status": "FAILED", "error": "missing workspace_id in job payload"}
        try:
            view = await container_for(self._services).workspace.recalculate_quota(
                RecalculateWorkspaceQuota(workspace_id=workspace_id)
            )
            return {"status": "SUCCEEDED", "workspace": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class WorkspaceCleanupArchivedJobHandler:
    job_type = "workspace.cleanup.archived"

    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "cleaned_count": 0}

