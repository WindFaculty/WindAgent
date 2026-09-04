"""Unit tests for Workspace application services and handlers."""

from pathlib import Path

import pytest
from windagent.modules.workspace.application.commands import (
    AcquireWorkspaceLock,
    AddWorkspaceMember,
    ArchiveWorkspace,
    CreateWorkspace,
    CreateWorkspaceSnapshot,
    ReleaseWorkspaceLock,
    RemoveWorkspaceMember,
    RestoreWorkspace,
    UpdateWorkspace,
)
from windagent.modules.workspace.application.queries import (
    CheckWorkspaceAccess,
    GetWorkspace,
    GetWorkspaceBySlug,
    GetWorkspaceMembers,
    GetWorkspaceSnapshot,
    ListWorkspaceLocks,
    ValidateWorkspacePath,
)
from windagent.modules.workspace.application.services import WorkspaceService
from windagent.modules.workspace.domain.errors import (
    WorkspaceAccessDeniedError,
    WorkspaceSlugAlreadyExistsError,
    WorkspaceStaleVersionError,
)
from windagent.modules.workspace.infrastructure.memory import (
    InMemoryTransactionScope,
    InMemoryWorkspaceStore,
)


@pytest.fixture
def workspace_service(tmp_path: Path) -> tuple[WorkspaceService, InMemoryWorkspaceStore]:
    store = InMemoryWorkspaceStore()

    def _factory() -> InMemoryTransactionScope:
        return InMemoryTransactionScope(store)

    svc = WorkspaceService(transaction_factory=_factory)
    return svc, store


@pytest.mark.asyncio
async def test_workspace_crud_flow(
    workspace_service: tuple[WorkspaceService, InMemoryWorkspaceStore], tmp_path: Path
) -> None:
    svc, store = workspace_service

    # Create workspace
    view = await svc.create_workspace(
        CreateWorkspace(
            name="Studio Alpha",
            slug="studio-alpha",
            root_path=str(tmp_path),
            owner_id="owner_1",
            description="Alpha workspace",
            tier="PRO",
        )
    )

    assert view.name == "Studio Alpha"
    assert view.slug == "studio-alpha"
    assert view.tier == "PRO"
    assert view.status == "ACTIVE"
    assert view.members_count == 1
    assert view.optimistic_version == 1

    # Duplicate slug rejected
    with pytest.raises(WorkspaceSlugAlreadyExistsError):
        await svc.create_workspace(
            CreateWorkspace(
                name="Studio Alpha 2",
                slug="studio-alpha",
                root_path=str(tmp_path),
                owner_id="owner_2",
            )
        )

    # Get by ID
    fetched = await svc.get_workspace(GetWorkspace(workspace_id=view.workspace_id))
    assert fetched is not None
    assert fetched.workspace_id == view.workspace_id

    # Get by slug
    fetched_slug = await svc.get_workspace_by_slug(GetWorkspaceBySlug(slug="studio-alpha"))
    assert fetched_slug is not None
    assert fetched_slug.workspace_id == view.workspace_id

    # Update workspace
    updated = await svc.update_workspace(
        UpdateWorkspace(
            workspace_id=view.workspace_id,
            expected_version=1,
            name="Studio Alpha Prime",
        )
    )
    assert updated.name == "Studio Alpha Prime"
    assert updated.optimistic_version == 2

    # Stale version rejected
    with pytest.raises(WorkspaceStaleVersionError):
        await svc.update_workspace(
            UpdateWorkspace(
                workspace_id=view.workspace_id,
                expected_version=1,
                name="Old update",
            )
        )

    # Archive and Restore
    archived = await svc.archive_workspace(
        ArchiveWorkspace(workspace_id=view.workspace_id, expected_version=2)
    )
    assert archived.status == "ARCHIVED"
    assert archived.optimistic_version == 3

    restored = await svc.restore_workspace(
        RestoreWorkspace(workspace_id=view.workspace_id, expected_version=3)
    )
    assert restored.status == "ACTIVE"
    assert restored.optimistic_version == 4


@pytest.mark.asyncio
async def test_workspace_membership_and_access(
    workspace_service: tuple[WorkspaceService, InMemoryWorkspaceStore], tmp_path: Path
) -> None:
    svc, store = workspace_service

    ws = await svc.create_workspace(
        CreateWorkspace(
            name="Team WS",
            slug="team-ws",
            root_path=str(tmp_path),
            owner_id="admin_user",
        )
    )

    # Add member by admin
    mem_view = await svc.add_member(
        AddWorkspaceMember(
            workspace_id=ws.workspace_id,
            user_id="dev_user",
            role="MEMBER",
            actor_id="admin_user",
        )
    )
    assert mem_view.user_id == "dev_user"
    assert mem_view.role == "MEMBER"

    # Non-admin cannot add member
    with pytest.raises(WorkspaceAccessDeniedError):
        await svc.add_member(
            AddWorkspaceMember(
                workspace_id=ws.workspace_id,
                user_id="other_user",
                role="VIEWER",
                actor_id="dev_user",
            )
        )

    # Check access permissions
    has_admin = await svc.check_access(
        CheckWorkspaceAccess(
            workspace_id=ws.workspace_id,
            user_id="admin_user",
            required_role="ADMIN",
        )
    )
    assert has_admin is True

    has_write = await svc.check_access(
        CheckWorkspaceAccess(
            workspace_id=ws.workspace_id,
            user_id="dev_user",
            required_role="MEMBER",
        )
    )
    assert has_write is True

    # List members
    members = await svc.get_members(GetWorkspaceMembers(workspace_id=ws.workspace_id))
    assert len(members) == 2

    # Remove member
    removed = await svc.remove_member(
        RemoveWorkspaceMember(
            workspace_id=ws.workspace_id,
            user_id="dev_user",
            actor_id="admin_user",
        )
    )
    assert removed is True


@pytest.mark.asyncio
async def test_workspace_locking_and_snapshot(
    workspace_service: tuple[WorkspaceService, InMemoryWorkspaceStore], tmp_path: Path
) -> None:
    svc, store = workspace_service

    ws = await svc.create_workspace(
        CreateWorkspace(
            name="Locks WS",
            slug="locks-ws",
            root_path=str(tmp_path),
            owner_id="owner_1",
        )
    )

    # Acquire lock
    lck = await svc.acquire_lock(
        AcquireWorkspaceLock(
            workspace_id=ws.workspace_id,
            resource_type="script",
            resource_id="sc_1",
            holder_id="agent_1",
            ttl_seconds=3600,
        )
    )
    assert lck.resource_id == "sc_1"
    assert lck.fencing_token == 1

    # List locks
    locks = await svc.list_locks(ListWorkspaceLocks(workspace_id=ws.workspace_id))
    assert len(locks) == 1

    # Release lock
    released = await svc.release_lock(
        ReleaseWorkspaceLock(
            workspace_id=ws.workspace_id,
            resource_id="sc_1",
            holder_id="agent_1",
        )
    )
    assert released is True

    # Snapshot
    snap = await svc.create_snapshot(CreateWorkspaceSnapshot(workspace_id=ws.workspace_id))
    assert snap.workspace_id == ws.workspace_id
    assert snap.slug == "locks-ws"

    fetched_snap = await svc.get_snapshot(GetWorkspaceSnapshot(workspace_id=ws.workspace_id))
    assert fetched_snap is not None
    assert fetched_snap.workspace_id == ws.workspace_id


@pytest.mark.asyncio
async def test_workspace_path_validation_service(
    workspace_service: tuple[WorkspaceService, InMemoryWorkspaceStore], tmp_path: Path
) -> None:
    svc, store = workspace_service

    ws = await svc.create_workspace(
        CreateWorkspace(
            name="Path WS",
            slug="path-ws",
            root_path=str(tmp_path),
            owner_id="owner_1",
        )
    )

    valid_res = await svc.validate_path(
        ValidateWorkspacePath(
            workspace_id=ws.workspace_id,
            target_path="assets/video.mp4",
        )
    )
    assert valid_res.valid is True
    assert valid_res.relative_path == "assets/video.mp4"

    invalid_res = await svc.validate_path(
        ValidateWorkspacePath(
            workspace_id=ws.workspace_id,
            target_path="../../outside.txt",
        )
    )
    assert invalid_res.valid is False
    assert invalid_res.error is not None
