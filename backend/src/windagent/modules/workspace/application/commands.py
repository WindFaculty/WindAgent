"""Command definitions for the Workspace bounded context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from windagent.platform.commands import Command

from .models import (
    WorkspaceLockView,
    WorkspaceMemberView,
    WorkspaceSnapshotView,
    WorkspaceView,
)


@dataclass(frozen=True, slots=True)
class CreateWorkspace(Command[WorkspaceView]):
    """Create a new workspace."""

    name: str
    slug: str
    root_path: str
    owner_id: str
    workspace_id: str | None = None
    description: str = ""
    tier: str = "LOCAL"
    quota: Mapping[str, Any] | None = None
    policy: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class UpdateWorkspace(Command[WorkspaceView]):
    """Update mutable workspace profile properties."""

    workspace_id: str
    expected_version: int
    name: str | None = None
    description: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ArchiveWorkspace(Command[WorkspaceView]):
    """Archive a workspace."""

    workspace_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class SuspendWorkspace(Command[WorkspaceView]):
    """Suspend a workspace."""

    workspace_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class RestoreWorkspace(Command[WorkspaceView]):
    """Restore an archived or suspended workspace to active state."""

    workspace_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class AddWorkspaceMember(Command[WorkspaceMemberView]):
    """Add a member or update existing member's role."""

    workspace_id: str
    user_id: str
    role: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class RemoveWorkspaceMember(Command[bool]):
    """Remove a member from the workspace."""

    workspace_id: str
    user_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class BindProjectToWorkspace(Command[WorkspaceView]):
    """Bind a project to the workspace."""

    workspace_id: str
    project_id: str


@dataclass(frozen=True, slots=True)
class UnbindProjectFromWorkspace(Command[WorkspaceView]):
    """Unbind a project from the workspace."""

    workspace_id: str
    project_id: str


@dataclass(frozen=True, slots=True)
class AcquireWorkspaceLock(Command[WorkspaceLockView]):
    """Acquire a resource lock within the workspace."""

    workspace_id: str
    resource_type: str
    resource_id: str
    holder_id: str
    ttl_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class ReleaseWorkspaceLock(Command[bool]):
    """Release a resource lock within the workspace."""

    workspace_id: str
    resource_id: str
    holder_id: str


@dataclass(frozen=True, slots=True)
class UpdateWorkspaceQuota(Command[WorkspaceView]):
    """Update workspace quota allocations."""

    workspace_id: str
    max_projects: int | None = None
    max_storage_bytes: int | None = None
    max_concurrent_runs: int | None = None
    max_credits_per_month: float | None = None


@dataclass(frozen=True, slots=True)
class UpdateWorkspacePolicy(Command[WorkspaceView]):
    """Update workspace execution and isolation policies."""

    workspace_id: str
    allowed_runtimes: tuple[str, ...] | None = None
    sandbox_mode: bool | None = None
    require_approvals: bool | None = None
    allow_shell: bool | None = None
    allow_network: bool | None = None


@dataclass(frozen=True, slots=True)
class CreateWorkspaceSnapshot(Command[WorkspaceSnapshotView]):
    """Generate and store a point-in-time snapshot."""

    workspace_id: str


@dataclass(frozen=True, slots=True)
class RecalculateWorkspaceQuota(Command[WorkspaceView]):
    """Background job command to recompute workspace usage metrics."""

    workspace_id: str
