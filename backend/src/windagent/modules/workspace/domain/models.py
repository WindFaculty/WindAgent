"""Workspace domain models, aggregates, and value objects."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now

from .errors import (
    InvalidWorkspaceStateTransitionError,
    WorkspaceAccessDeniedError,
    WorkspaceLockConflictError,
    WorkspaceQuotaExceededError,
)


def _ensure_entity_id(value: EntityId | str) -> EntityId:
    if isinstance(value, EntityId):
        return value
    try:
        return EntityId(value)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"workspace.{value}"))


class WorkspaceStatus(StrEnum):
    """Lifecycle state of a workspace."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class WorkspaceTier(StrEnum):
    """Billing and capability tier."""

    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"
    LOCAL = "LOCAL"


class WorkspaceRole(StrEnum):
    """Membership role within a workspace."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


    @property
    def can_admin(self) -> bool:
        return self in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    @property
    def can_write(self) -> bool:
        return self in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """A user membership entry in a workspace."""

    user_id: str
    role: WorkspaceRole
    joined_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class WorkspaceQuota:
    """Resource constraints allocated to a workspace."""

    max_projects: int = 50
    max_storage_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB
    max_concurrent_runs: int = 10
    max_credits_per_month: float = 1000.0


@dataclass(frozen=True, slots=True)
class WorkspaceQuotaUsage:
    """Current consumption of workspace resources."""

    current_projects: int = 0
    current_storage_bytes: int = 0
    current_concurrent_runs: int = 0
    used_credits: float = 0.0


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    """Execution and isolation security policy."""

    allowed_runtimes: tuple[str, ...] = ("in_process", "subprocess", "browser")
    sandbox_mode: bool = True
    require_approvals: bool = False
    allow_shell: bool = True
    allow_network: bool = True


@dataclass(frozen=True, slots=True)
class WorkspaceLock:
    """Distributed coordination lock on a resource within a workspace."""

    lock_id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    holder_id: str
    acquired_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    fencing_token: int = 1

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(UTC)
        return current > self.expires_at


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """Point-in-time export of workspace metadata and status."""

    workspace_id: str
    name: str
    slug: str
    status: WorkspaceStatus
    tier: WorkspaceTier
    owner_id: str
    root_path: str
    members_count: int
    projects_count: int
    quota: WorkspaceQuota
    quota_usage: WorkspaceQuotaUsage
    policy: WorkspacePolicy
    optimistic_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class WorkspaceAggregate:
    """The root domain aggregate managing workspace state and lifecycle."""

    id: EntityId
    name: str
    slug: str
    root_path: str
    owner_id: str
    description: str = ""
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    tier: WorkspaceTier = WorkspaceTier.LOCAL
    quota: WorkspaceQuota = field(default_factory=WorkspaceQuota)
    quota_usage: WorkspaceQuotaUsage = field(default_factory=WorkspaceQuotaUsage)
    policy: WorkspacePolicy = field(default_factory=WorkspacePolicy)
    members: dict[str, WorkspaceMember] = field(default_factory=dict)
    bound_project_ids: set[str] = field(default_factory=set)
    locks: dict[str, WorkspaceLock] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    optimistic_version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        workspace_id: EntityId | str,
        name: str,
        slug: str,
        root_path: str,
        owner_id: str,
        description: str = "",
        tier: WorkspaceTier = WorkspaceTier.LOCAL,
        quota: WorkspaceQuota | None = None,
        policy: WorkspacePolicy | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkspaceAggregate:
        """Factory method to instantiate a new WorkspaceAggregate."""
        now = utc_now()
        members = {
            owner_id: WorkspaceMember(
                user_id=owner_id,
                role=WorkspaceRole.OWNER,
                joined_at=now,
            )
        }
        return cls(
            id=_ensure_entity_id(workspace_id),
            name=name.strip(),
            slug=slug.strip().lower(),
            root_path=root_path.strip(),
            owner_id=owner_id.strip(),
            description=description.strip(),
            status=WorkspaceStatus.ACTIVE,
            tier=tier,
            quota=quota or WorkspaceQuota(),
            quota_usage=WorkspaceQuotaUsage(),
            policy=policy or WorkspacePolicy(),
            members=members,
            bound_project_ids=set(),
            locks={},
            metadata=dict(metadata or {}),
            optimistic_version=1,
            created_at=now,
            updated_at=now,
        )

    def update_info(
        self,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Update mutable workspace profile information."""
        self._ensure_not_archived()
        if name is not None:
            self.name = name.strip()
        if description is not None:
            self.description = description.strip()
        if metadata is not None:
            self.metadata.update(metadata)
        self.touch()

    def archive(self) -> None:
        """Transition workspace to ARCHIVED."""
        if self.status == WorkspaceStatus.ARCHIVED:
            return
        self.status = WorkspaceStatus.ARCHIVED
        self.locks.clear()
        self.touch()

    def suspend(self) -> None:
        """Transition workspace to SUSPENDED."""
        if self.status == WorkspaceStatus.ARCHIVED:
            raise InvalidWorkspaceStateTransitionError(
                str(self.id), self.status.value, WorkspaceStatus.SUSPENDED.value
            )
        self.status = WorkspaceStatus.SUSPENDED
        self.touch()

    def restore(self) -> None:
        """Restore workspace back to ACTIVE."""
        if self.status == WorkspaceStatus.ACTIVE:
            return
        self.status = WorkspaceStatus.ACTIVE
        self.touch()

    def add_or_update_member(self, user_id: str, role: WorkspaceRole) -> None:
        """Add a member or update existing member's role."""
        self._ensure_not_archived()
        if user_id == self.owner_id and role != WorkspaceRole.OWNER:
            raise WorkspaceAccessDeniedError(user_id, str(self.id), "demote workspace owner")
        self.members[user_id] = WorkspaceMember(user_id=user_id, role=role, joined_at=utc_now())
        self.touch()

    def remove_member(self, user_id: str) -> None:
        """Remove a member from the workspace."""
        self._ensure_not_archived()
        if user_id == self.owner_id:
            raise WorkspaceAccessDeniedError(user_id, str(self.id), "remove workspace owner")
        if user_id in self.members:
            del self.members[user_id]
            self.touch()

    def bind_project(self, project_id: str) -> None:
        """Bind a project to this workspace, respecting project quota."""
        self._ensure_not_archived()
        if project_id in self.bound_project_ids:
            return
        if len(self.bound_project_ids) >= self.quota.max_projects:
            raise WorkspaceQuotaExceededError(
                workspace_id=str(self.id),
                resource="projects",
                limit=self.quota.max_projects,
                current=len(self.bound_project_ids),
            )
        self.bound_project_ids.add(project_id)
        self._recalculate_usage()
        self.touch()

    def unbind_project(self, project_id: str) -> None:
        """Unbind a project from this workspace."""
        self._ensure_not_archived()
        if project_id in self.bound_project_ids:
            self.bound_project_ids.remove(project_id)
            self._recalculate_usage()
            self.touch()

    def acquire_lock(
        self,
        lock_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        expires_at: datetime | None = None,
    ) -> WorkspaceLock:
        """Acquire a resource lock within the workspace."""
        self._ensure_active()
        existing = self.locks.get(resource_id)
        if existing and not existing.is_expired():
            if existing.holder_id != holder_id:
                raise WorkspaceLockConflictError(resource_id, existing.holder_id)
            # Re-acquire / extend
            token = existing.fencing_token + 1
        else:
            token = (existing.fencing_token + 1) if existing else 1

        lock = WorkspaceLock(
            lock_id=lock_id,
            workspace_id=str(self.id),
            resource_type=resource_type,
            resource_id=resource_id,
            holder_id=holder_id,
            acquired_at=utc_now(),
            expires_at=expires_at,
            fencing_token=token,
        )
        self.locks[resource_id] = lock
        self.touch()
        return lock

    def release_lock(self, resource_id: str, holder_id: str) -> None:
        """Release a resource lock if held by holder_id."""
        existing = self.locks.get(resource_id)
        if not existing:
            return
        if existing.holder_id != holder_id:
            raise WorkspaceAccessDeniedError(holder_id, str(self.id), f"release lock on {resource_id}")
        del self.locks[resource_id]
        self.touch()

    def update_quota(self, new_quota: WorkspaceQuota) -> None:
        """Update quota parameters."""
        self.quota = new_quota
        self.touch()

    def update_policy(self, new_policy: WorkspacePolicy) -> None:
        """Update execution and security policy."""
        self.policy = new_policy
        self.touch()

    def update_usage(
        self,
        storage_bytes: int | None = None,
        concurrent_runs: int | None = None,
        added_credits: float = 0.0,
    ) -> None:
        """Update current consumption metrics and verify quota limits."""
        cur_storage = storage_bytes if storage_bytes is not None else self.quota_usage.current_storage_bytes
        cur_runs = concurrent_runs if concurrent_runs is not None else self.quota_usage.current_concurrent_runs
        cur_credits = self.quota_usage.used_credits + added_credits

        if cur_storage > self.quota.max_storage_bytes:
            raise WorkspaceQuotaExceededError(
                str(self.id), "storage_bytes", self.quota.max_storage_bytes, cur_storage
            )
        if cur_runs > self.quota.max_concurrent_runs:
            raise WorkspaceQuotaExceededError(
                str(self.id), "concurrent_runs", self.quota.max_concurrent_runs, cur_runs
            )

        self.quota_usage = WorkspaceQuotaUsage(
            current_projects=len(self.bound_project_ids),
            current_storage_bytes=cur_storage,
            current_concurrent_runs=cur_runs,
            used_credits=cur_credits,
        )
        self.touch()

    def touch(self) -> None:
        """Advance optimistic version and updated_at timestamp."""
        self.optimistic_version += 1
        self.updated_at = utc_now()

    def to_snapshot(self) -> WorkspaceSnapshot:
        """Create an immutable snapshot of current aggregate state."""
        return WorkspaceSnapshot(
            workspace_id=str(self.id),
            name=self.name,
            slug=self.slug,
            status=self.status,
            tier=self.tier,
            owner_id=self.owner_id,
            root_path=self.root_path,
            members_count=len(self.members),
            projects_count=len(self.bound_project_ids),
            quota=self.quota,
            quota_usage=self.quota_usage,
            policy=self.policy,
            optimistic_version=self.optimistic_version,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def _ensure_not_archived(self) -> None:
        if self.status == WorkspaceStatus.ARCHIVED:
            raise InvalidWorkspaceStateTransitionError(
                str(self.id), self.status.value, "MUTATION_ON_ARCHIVED"
            )

    def _ensure_active(self) -> None:
        if self.status != WorkspaceStatus.ACTIVE:
            raise InvalidWorkspaceStateTransitionError(
                str(self.id), self.status.value, "MUTATION_ON_INACTIVE"
            )

    def _recalculate_usage(self) -> None:
        self.quota_usage = WorkspaceQuotaUsage(
            current_projects=len(self.bound_project_ids),
            current_storage_bytes=self.quota_usage.current_storage_bytes,
            current_concurrent_runs=self.quota_usage.current_concurrent_runs,
            used_credits=self.quota_usage.used_credits,
        )
