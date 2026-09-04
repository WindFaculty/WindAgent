"""Unit tests for Workspace domain models, aggregates, and sandbox isolation."""

from pathlib import Path

import pytest
from windagent.kernel.ids import EntityId
from windagent.modules.workspace.domain.errors import (
    InvalidWorkspaceStateTransitionError,
    WorkspaceAccessDeniedError,
    WorkspaceLockConflictError,
    WorkspacePathViolationError,
    WorkspaceQuotaExceededError,
)
from windagent.modules.workspace.domain.models import (
    WorkspaceAggregate,
    WorkspaceQuota,
    WorkspaceRole,
    WorkspaceStatus,
    WorkspaceTier,
)
from windagent.modules.workspace.domain.sandbox import WorkspaceSandbox


def test_workspace_aggregate_creation(tmp_path: Path) -> None:
    ws_id = EntityId.generate()
    agg = WorkspaceAggregate.create(
        workspace_id=ws_id,
        name="Test Workspace",
        slug="test-workspace",
        root_path=str(tmp_path),
        owner_id="user_owner",
        description="A test workspace",
        tier=WorkspaceTier.PRO,
    )

    assert agg.id == ws_id
    assert agg.name == "Test Workspace"
    assert agg.slug == "test-workspace"
    assert agg.status == WorkspaceStatus.ACTIVE
    assert agg.tier == WorkspaceTier.PRO
    assert agg.owner_id == "user_owner"
    assert "user_owner" in agg.members
    assert agg.members["user_owner"].role == WorkspaceRole.OWNER
    assert agg.optimistic_version == 1


def test_workspace_member_management(tmp_path: Path) -> None:
    agg = WorkspaceAggregate.create(
        workspace_id=EntityId.generate(),
        name="Mem WS",
        slug="mem-ws",
        root_path=str(tmp_path),
        owner_id="owner1",
    )

    agg.add_or_update_member("alice", WorkspaceRole.MEMBER)
    assert "alice" in agg.members
    assert agg.members["alice"].role == WorkspaceRole.MEMBER
    assert agg.optimistic_version == 2

    # Update role
    agg.add_or_update_member("alice", WorkspaceRole.ADMIN)
    assert agg.members["alice"].role == WorkspaceRole.ADMIN
    assert agg.optimistic_version == 3

    # Remove member
    agg.remove_member("alice")
    assert "alice" not in agg.members
    assert agg.optimistic_version == 4

    # Cannot remove owner
    with pytest.raises(WorkspaceAccessDeniedError):
        agg.remove_member("owner1")

    # Cannot demote owner
    with pytest.raises(WorkspaceAccessDeniedError):
        agg.add_or_update_member("owner1", WorkspaceRole.VIEWER)


def test_workspace_project_binding_and_quota(tmp_path: Path) -> None:
    quota = WorkspaceQuota(max_projects=2)
    agg = WorkspaceAggregate.create(
        workspace_id=EntityId.generate(),
        name="Quota WS",
        slug="quota-ws",
        root_path=str(tmp_path),
        owner_id="owner1",
        quota=quota,
    )

    agg.bind_project("proj_1")
    agg.bind_project("proj_2")
    assert len(agg.bound_project_ids) == 2
    assert agg.quota_usage.current_projects == 2

    # Idempotent re-bind
    agg.bind_project("proj_2")
    assert len(agg.bound_project_ids) == 2

    # Exceeding quota
    with pytest.raises(WorkspaceQuotaExceededError):
        agg.bind_project("proj_3")

    # Unbind
    agg.unbind_project("proj_1")
    assert len(agg.bound_project_ids) == 1
    assert agg.quota_usage.current_projects == 1


def test_workspace_locking(tmp_path: Path) -> None:
    agg = WorkspaceAggregate.create(
        workspace_id=EntityId.generate(),
        name="Lock WS",
        slug="lock-ws",
        root_path=str(tmp_path),
        owner_id="owner1",
    )

    lock1 = agg.acquire_lock(
        lock_id="lck_1",
        resource_type="storyboard",
        resource_id="sb_100",
        holder_id="agent_alpha",
    )
    assert lock1.fencing_token == 1
    assert lock1.holder_id == "agent_alpha"

    # Same holder re-acquires / extends
    lock1_ext = agg.acquire_lock(
        lock_id="lck_1_ext",
        resource_type="storyboard",
        resource_id="sb_100",
        holder_id="agent_alpha",
    )
    assert lock1_ext.fencing_token == 2

    # Another holder conflict
    with pytest.raises(WorkspaceLockConflictError):
        agg.acquire_lock(
            lock_id="lck_2",
            resource_type="storyboard",
            resource_id="sb_100",
            holder_id="agent_beta",
        )

    # Release by wrong holder
    with pytest.raises(WorkspaceAccessDeniedError):
        agg.release_lock("sb_100", "agent_beta")

    # Release by correct holder
    agg.release_lock("sb_100", "agent_alpha")
    assert "sb_100" not in agg.locks


def test_workspace_state_transitions(tmp_path: Path) -> None:
    agg = WorkspaceAggregate.create(
        workspace_id=EntityId.generate(),
        name="Trans WS",
        slug="trans-ws",
        root_path=str(tmp_path),
        owner_id="owner1",
    )

    agg.suspend()
    assert agg.status == WorkspaceStatus.SUSPENDED

    agg.restore()
    assert agg.status == WorkspaceStatus.ACTIVE

    agg.archive()
    assert agg.status == WorkspaceStatus.ARCHIVED

    # Cannot mutate archived
    with pytest.raises(InvalidWorkspaceStateTransitionError):
        agg.suspend()

    with pytest.raises(InvalidWorkspaceStateTransitionError):
        agg.add_or_update_member("bob", WorkspaceRole.MEMBER)


def test_workspace_sandbox_containment(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    assert sandbox.root == tmp_path.resolve()

    # Valid relative subpath
    valid_sub = sandbox.validate_path("sub/folder/file.txt")
    assert valid_sub == (tmp_path / "sub" / "folder" / "file.txt").resolve()
    assert sandbox.relative_to_root("sub/folder/file.txt") == "sub/folder/file.txt"

    # Empty path
    with pytest.raises(WorkspacePathViolationError):
        sandbox.validate_path("")

    # Path traversal escape
    with pytest.raises(WorkspacePathViolationError):
        sandbox.validate_path("../../etc/passwd")

    # Null byte
    with pytest.raises(WorkspacePathViolationError):
        sandbox.validate_path("sub\0folder")
