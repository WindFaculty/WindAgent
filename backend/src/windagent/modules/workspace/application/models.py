"""View models and durable row definitions for the Workspace module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkspaceRow:
    """Storage row shape for workspace_workspaces table."""

    workspace_id: str
    name: str
    slug: str
    root_path: str
    owner_id: str
    description: str
    status: str
    tier: str
    quota_json: str
    quota_usage_json: str
    policy_json: str
    metadata_json: str
    optimistic_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceMemberRow:
    """Storage row shape for workspace_members table."""

    workspace_id: str
    user_id: str
    role: str
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceProjectBindingRow:
    """Storage row shape for workspace_project_bindings table."""

    workspace_id: str
    project_id: str
    bound_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceLockRow:
    """Storage row shape for workspace_locks table."""

    lock_id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    holder_id: str
    acquired_at: datetime
    expires_at: datetime | None
    fencing_token: int


@dataclass(frozen=True, slots=True)
class WorkspaceView:
    """API and command-bus view of a workspace."""

    workspace_id: str
    name: str
    slug: str
    root_path: str
    owner_id: str
    description: str
    status: str
    tier: str
    quota: dict[str, Any]
    quota_usage: dict[str, Any]
    policy: dict[str, Any]
    members_count: int
    projects_count: int
    optimistic_version: int
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "slug": self.slug,
            "root_path": self.root_path,
            "owner_id": self.owner_id,
            "description": self.description,
            "status": self.status,
            "tier": self.tier,
            "quota": self.quota,
            "quota_usage": self.quota_usage,
            "policy": self.policy,
            "members_count": self.members_count,
            "projects_count": self.projects_count,
            "optimistic_version": self.optimistic_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceMemberView:
    """API view of a workspace member."""

    workspace_id: str
    user_id: str
    role: str
    joined_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceLockView:
    """API view of a workspace lock."""

    lock_id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    holder_id: str
    acquired_at: str
    expires_at: str | None
    fencing_token: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "workspace_id": self.workspace_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "holder_id": self.holder_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "fencing_token": self.fencing_token,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotView:
    """API view of a workspace snapshot."""

    workspace_id: str
    name: str
    slug: str
    status: str
    tier: str
    owner_id: str
    root_path: str
    members_count: int
    projects_count: int
    quota: dict[str, Any]
    quota_usage: dict[str, Any]
    policy: dict[str, Any]
    optimistic_version: int
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "tier": self.tier,
            "owner_id": self.owner_id,
            "root_path": self.root_path,
            "members_count": self.members_count,
            "projects_count": self.projects_count,
            "quota": self.quota,
            "quota_usage": self.quota_usage,
            "policy": self.policy,
            "optimistic_version": self.optimistic_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class PathValidationView:
    """API view of a path validation result."""

    workspace_id: str
    valid: bool
    resolved_path: str
    relative_path: str
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "valid": self.valid,
            "resolved_path": self.resolved_path,
            "relative_path": self.relative_path,
            "error": self.error,
        }
