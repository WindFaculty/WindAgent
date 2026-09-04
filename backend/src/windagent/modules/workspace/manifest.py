"""Module manifest for the Workspace bounded context."""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_workspace_router
from .application.commands import (
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
from .application.handlers import (
    AcquireWorkspaceLockHandler,
    AddWorkspaceMemberHandler,
    ArchiveWorkspaceHandler,
    BindProjectToWorkspaceHandler,
    CheckWorkspaceAccessHandler,
    CreateWorkspaceHandler,
    CreateWorkspaceSnapshotHandler,
    GetWorkspaceBySlugHandler,
    GetWorkspaceHandler,
    GetWorkspaceMembersHandler,
    GetWorkspaceSnapshotHandler,
    ListWorkspaceLocksHandler,
    ListWorkspacesHandler,
    RecalculateWorkspaceQuotaHandler,
    ReleaseWorkspaceLockHandler,
    RemoveWorkspaceMemberHandler,
    RestoreWorkspaceHandler,
    SuspendWorkspaceHandler,
    UnbindProjectFromWorkspaceHandler,
    UpdateWorkspaceHandler,
    UpdateWorkspacePolicyHandler,
    UpdateWorkspaceQuotaHandler,
    ValidateWorkspacePathHandler,
    WorkspaceCleanupArchivedJobHandler,
    WorkspaceQuotaRecalculateJobHandler,
)
from .application.queries import (
    CheckWorkspaceAccess,
    GetWorkspace,
    GetWorkspaceBySlug,
    GetWorkspaceMembers,
    GetWorkspaceSnapshot,
    ListWorkspaceLocks,
    ListWorkspaces,
    ValidateWorkspacePath,
)
from .application.runtime import WorkspaceServices


def build_workspace_manifest(services: WorkspaceServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateWorkspace, CreateWorkspaceHandler(services)),
            CommandRegistration(UpdateWorkspace, UpdateWorkspaceHandler(services)),
            CommandRegistration(ArchiveWorkspace, ArchiveWorkspaceHandler(services)),
            CommandRegistration(SuspendWorkspace, SuspendWorkspaceHandler(services)),
            CommandRegistration(RestoreWorkspace, RestoreWorkspaceHandler(services)),
            CommandRegistration(AddWorkspaceMember, AddWorkspaceMemberHandler(services)),
            CommandRegistration(RemoveWorkspaceMember, RemoveWorkspaceMemberHandler(services)),
            CommandRegistration(BindProjectToWorkspace, BindProjectToWorkspaceHandler(services)),
            CommandRegistration(UnbindProjectFromWorkspace, UnbindProjectFromWorkspaceHandler(services)),
            CommandRegistration(AcquireWorkspaceLock, AcquireWorkspaceLockHandler(services)),
            CommandRegistration(ReleaseWorkspaceLock, ReleaseWorkspaceLockHandler(services)),
            CommandRegistration(UpdateWorkspaceQuota, UpdateWorkspaceQuotaHandler(services)),
            CommandRegistration(UpdateWorkspacePolicy, UpdateWorkspacePolicyHandler(services)),
            CommandRegistration(CreateWorkspaceSnapshot, CreateWorkspaceSnapshotHandler(services)),
            CommandRegistration(RecalculateWorkspaceQuota, RecalculateWorkspaceQuotaHandler(services)),
        ),
        queries=(
            QueryRegistration(GetWorkspace, GetWorkspaceHandler(services)),
            QueryRegistration(GetWorkspaceBySlug, GetWorkspaceBySlugHandler(services)),
            QueryRegistration(ListWorkspaces, ListWorkspacesHandler(services)),
            QueryRegistration(GetWorkspaceMembers, GetWorkspaceMembersHandler(services)),
            QueryRegistration(GetWorkspaceSnapshot, GetWorkspaceSnapshotHandler(services)),
            QueryRegistration(ListWorkspaceLocks, ListWorkspaceLocksHandler(services)),
            QueryRegistration(ValidateWorkspacePath, ValidateWorkspacePathHandler(services)),
            QueryRegistration(CheckWorkspaceAccess, CheckWorkspaceAccessHandler(services)),
        ),
        jobs=(
            JobRegistration("workspace.quota.recalculate", WorkspaceQuotaRecalculateJobHandler(services)),
            JobRegistration("workspace.cleanup.archived", WorkspaceCleanupArchivedJobHandler(services)),
        ),
        routers=(create_workspace_router(),),
        capabilities=(
            "workspace",
            "tenancy",
            "sandbox",
            "quotas",
            "locks",
            "project_binding",
            "members",
            "snapshots",
        ),
    )


manifest = build_workspace_manifest()
