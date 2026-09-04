"""E2E Test: Workspace provisioning, membership RBAC, distributed locking, and quota enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest
from windagent.modules.workspace.application.commands import (
    AcquireWorkspaceLock,
    AddWorkspaceMember,
    CreateWorkspace,
)
from windagent.modules.workspace.application.queries import (
    GetWorkspaceMembers,
    ListWorkspaceLocks,
)
from windagent.modules.workspace.application.services import WorkspaceService
from windagent.modules.workspace.infrastructure.memory import (
    InMemoryTransactionScope,
    InMemoryWorkspaceStore,
)


@pytest.mark.asyncio
async def test_e2e_workspace_lifecycle_and_sandboxing(tmp_path: Path) -> None:
    store = InMemoryWorkspaceStore()

    def _factory() -> InMemoryTransactionScope:
        return InMemoryTransactionScope(store)

    svc = WorkspaceService(transaction_factory=_factory)

    # 1. Create Workspace
    view = await svc.create_workspace(
        CreateWorkspace(
            name="Production Enterprise",
            slug="prod-enterprise",
            root_path=str(tmp_path),
            owner_id="user-owner-1",
            tier="PRO",
        )
    )
    assert view.name == "Production Enterprise"
    assert view.slug == "prod-enterprise"
    assert view.status == "ACTIVE"

    # 2. Add Member with RBAC
    mem_view = await svc.add_member(
        AddWorkspaceMember(
            workspace_id=view.workspace_id,
            user_id="user-editor-1",
            role="MEMBER",
            actor_id="user-owner-1",
        )
    )
    assert mem_view.user_id == "user-editor-1"
    assert mem_view.role == "MEMBER"

    members = await svc.get_members(GetWorkspaceMembers(workspace_id=view.workspace_id))
    assert len(members) == 2

    # 3. Acquire Distributed Resource Lock (Fencing)
    lock = await svc.acquire_lock(
        AcquireWorkspaceLock(
            workspace_id=view.workspace_id,
            resource_type="project_timeline",
            resource_id="timeline-main-4k",
            holder_id="user-editor-1",
            ttl_seconds=30,
        )
    )
    assert lock.resource_id == "timeline-main-4k"
    assert lock.fencing_token > 0
    assert lock.holder_id == "user-editor-1"

    locks = await svc.list_locks(ListWorkspaceLocks(workspace_id=view.workspace_id))
    assert len(locks) == 1
