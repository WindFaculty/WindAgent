"""Query definitions for the Workspace bounded context."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import (
    PathValidationView,
    WorkspaceLockView,
    WorkspaceMemberView,
    WorkspaceSnapshotView,
    WorkspaceView,
)


@dataclass(frozen=True, slots=True)
class GetWorkspace(Query[WorkspaceView | None]):
    """Fetch workspace by ID."""

    workspace_id: str


@dataclass(frozen=True, slots=True)
class GetWorkspaceBySlug(Query[WorkspaceView | None]):
    """Fetch workspace by unique slug."""

    slug: str


@dataclass(frozen=True, slots=True)
class ListWorkspaces(Query[list[WorkspaceView]]):
    """List workspaces with optional owner and status filters."""

    owner_id: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetWorkspaceMembers(Query[list[WorkspaceMemberView]]):
    """List all members of a workspace."""

    workspace_id: str


@dataclass(frozen=True, slots=True)
class GetWorkspaceSnapshot(Query[WorkspaceSnapshotView | None]):
    """Get the latest snapshot for a workspace."""

    workspace_id: str


@dataclass(frozen=True, slots=True)
class ListWorkspaceLocks(Query[list[WorkspaceLockView]]):
    """List all active resource locks in a workspace."""

    workspace_id: str


@dataclass(frozen=True, slots=True)
class ValidateWorkspacePath(Query[PathValidationView]):
    """Validate a path against the workspace sandbox directory root."""

    workspace_id: str
    target_path: str


@dataclass(frozen=True, slots=True)
class CheckWorkspaceAccess(Query[bool]):
    """Check if an actor has requested permission level on a workspace."""

    workspace_id: str
    user_id: str
    required_role: str = "VIEWER"
