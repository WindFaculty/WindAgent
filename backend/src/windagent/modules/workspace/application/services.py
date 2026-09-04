"""Application service for orchestrating workspace operations."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from windagent.kernel.ids import EntityId

from ..domain.errors import (
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
    WorkspacePathViolationError,
    WorkspaceSlugAlreadyExistsError,
    WorkspaceStaleVersionError,
)
from ..domain.models import (
    WorkspaceAggregate,
    WorkspaceLock,
    WorkspaceMember,
    WorkspacePolicy,
    WorkspaceQuota,
    WorkspaceRole,
    WorkspaceSnapshot,
    WorkspaceTier,
)
from ..domain.sandbox import WorkspaceSandbox
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
from .events import workspace_events
from .models import (
    PathValidationView,
    WorkspaceLockView,
    WorkspaceMemberView,
    WorkspaceSnapshotView,
    WorkspaceView,
)
from .ports import TransactionScope
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


def _to_view(agg: WorkspaceAggregate) -> WorkspaceView:
    return WorkspaceView(
        workspace_id=str(agg.id),
        name=agg.name,
        slug=agg.slug,
        root_path=agg.root_path,
        owner_id=agg.owner_id,
        description=agg.description,
        status=agg.status.value,
        tier=agg.tier.value,
        quota={
            "max_projects": agg.quota.max_projects,
            "max_storage_bytes": agg.quota.max_storage_bytes,
            "max_concurrent_runs": agg.quota.max_concurrent_runs,
            "max_credits_per_month": agg.quota.max_credits_per_month,
        },
        quota_usage={
            "current_projects": agg.quota_usage.current_projects,
            "current_storage_bytes": agg.quota_usage.current_storage_bytes,
            "current_concurrent_runs": agg.quota_usage.current_concurrent_runs,
            "used_credits": agg.quota_usage.used_credits,
        },
        policy={
            "allowed_runtimes": list(agg.policy.allowed_runtimes),
            "sandbox_mode": agg.policy.sandbox_mode,
            "require_approvals": agg.policy.require_approvals,
            "allow_shell": agg.policy.allow_shell,
            "allow_network": agg.policy.allow_network,
        },
        members_count=len(agg.members),
        projects_count=len(agg.bound_project_ids),
        optimistic_version=agg.optimistic_version,
        created_at=agg.created_at.isoformat(),
        updated_at=agg.updated_at.isoformat(),
        metadata=dict(agg.metadata),
    )


def _to_member_view(member: WorkspaceMember, workspace_id: str) -> WorkspaceMemberView:
    return WorkspaceMemberView(
        workspace_id=workspace_id,
        user_id=member.user_id,
        role=member.role.value,
        joined_at=member.joined_at.isoformat(),
    )


def _to_lock_view(lock: WorkspaceLock) -> WorkspaceLockView:
    return WorkspaceLockView(
        lock_id=lock.lock_id,
        workspace_id=lock.workspace_id,
        resource_type=lock.resource_type,
        resource_id=lock.resource_id,
        holder_id=lock.holder_id,
        acquired_at=lock.acquired_at.isoformat(),
        expires_at=lock.expires_at.isoformat() if lock.expires_at else None,
        fencing_token=lock.fencing_token,
    )


def _to_snapshot_view(snap: WorkspaceSnapshot) -> WorkspaceSnapshotView:
    return WorkspaceSnapshotView(
        workspace_id=snap.workspace_id,
        name=snap.name,
        slug=snap.slug,
        status=snap.status.value,
        tier=snap.tier.value,
        owner_id=snap.owner_id,
        root_path=snap.root_path,
        members_count=snap.members_count,
        projects_count=snap.projects_count,
        quota={
            "max_projects": snap.quota.max_projects,
            "max_storage_bytes": snap.quota.max_storage_bytes,
            "max_concurrent_runs": snap.quota.max_concurrent_runs,
            "max_credits_per_month": snap.quota.max_credits_per_month,
        },
        quota_usage={
            "current_projects": snap.quota_usage.current_projects,
            "current_storage_bytes": snap.quota_usage.current_storage_bytes,
            "current_concurrent_runs": snap.quota_usage.current_concurrent_runs,
            "used_credits": snap.quota_usage.used_credits,
        },
        policy={
            "allowed_runtimes": list(snap.policy.allowed_runtimes),
            "sandbox_mode": snap.policy.sandbox_mode,
            "require_approvals": snap.policy.require_approvals,
            "allow_shell": snap.policy.allow_shell,
            "allow_network": snap.policy.allow_network,
        },
        optimistic_version=snap.optimistic_version,
        created_at=snap.created_at.isoformat(),
        updated_at=snap.updated_at.isoformat(),
    )


def _to_entity_id(val: str | None) -> EntityId:
    if not val:
        return EntityId.generate()
    try:
        return EntityId(val)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"workspace.{val}"))


class WorkspaceService:
    """Service handling workspace commands and queries."""

    def __init__(self, transaction_factory: Callable[[], TransactionScope]) -> None:
        self._tx_factory = transaction_factory

    async def create_workspace(self, cmd: CreateWorkspace) -> WorkspaceView:
        ws_id = _to_entity_id(cmd.workspace_id)
        slug = cmd.slug.strip().lower()

        # Validate sandbox path
        sandbox = WorkspaceSandbox(cmd.root_path)

        async with self._tx_factory() as tx:
            existing = await tx.store.get_by_slug(slug)
            if existing is not None:
                raise WorkspaceSlugAlreadyExistsError(slug)

            quota = WorkspaceQuota(**dict(cmd.quota or {})) if cmd.quota else None
            policy = WorkspacePolicy(**dict(cmd.policy or {})) if cmd.policy else None
            tier = WorkspaceTier(cmd.tier) if cmd.tier in WorkspaceTier.__members__ else WorkspaceTier.LOCAL

            agg = WorkspaceAggregate.create(
                workspace_id=ws_id,
                name=cmd.name,
                slug=slug,
                root_path=str(sandbox.root),
                owner_id=cmd.owner_id,
                description=cmd.description,
                tier=tier,
                quota=quota,
                policy=policy,
                metadata=cmd.metadata,
            )

            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_created(
                    workspace_id=str(agg.id),
                    slug=agg.slug,
                    name=agg.name,
                    owner_id=agg.owner_id,
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def update_workspace(self, cmd: UpdateWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)
            if agg.optimistic_version != cmd.expected_version:
                raise WorkspaceStaleVersionError(
                    cmd.workspace_id, cmd.expected_version, agg.optimistic_version
                )

            agg.update_info(name=cmd.name, description=cmd.description, metadata=cmd.metadata)
            await tx.store.save(agg, expected_version=cmd.expected_version)
            tx.record_event(
                workspace_events.workspace_updated(
                    workspace_id=str(agg.id),
                    version=agg.optimistic_version,
                    name=agg.name,
                    status=agg.status.value,
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def archive_workspace(self, cmd: ArchiveWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)
            if agg.optimistic_version != cmd.expected_version:
                raise WorkspaceStaleVersionError(
                    cmd.workspace_id, cmd.expected_version, agg.optimistic_version
                )

            agg.archive()
            await tx.store.save(agg, expected_version=cmd.expected_version)
            tx.record_event(workspace_events.workspace_archived(str(agg.id)))
            await tx.commit()
            return _to_view(agg)

    async def suspend_workspace(self, cmd: SuspendWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)
            if agg.optimistic_version != cmd.expected_version:
                raise WorkspaceStaleVersionError(
                    cmd.workspace_id, cmd.expected_version, agg.optimistic_version
                )

            agg.suspend()
            await tx.store.save(agg, expected_version=cmd.expected_version)
            tx.record_event(
                workspace_events.workspace_updated(
                    str(agg.id), agg.optimistic_version, status=agg.status.value
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def restore_workspace(self, cmd: RestoreWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)
            if agg.optimistic_version != cmd.expected_version:
                raise WorkspaceStaleVersionError(
                    cmd.workspace_id, cmd.expected_version, agg.optimistic_version
                )

            agg.restore()
            await tx.store.save(agg, expected_version=cmd.expected_version)
            tx.record_event(
                workspace_events.workspace_updated(
                    str(agg.id), agg.optimistic_version, status=agg.status.value
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def add_member(self, cmd: AddWorkspaceMember) -> WorkspaceMemberView:
        role = WorkspaceRole(cmd.role) if cmd.role in WorkspaceRole.__members__ else WorkspaceRole.MEMBER
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            actor = agg.members.get(cmd.actor_id)
            if not actor or not actor.role.can_admin:
                raise WorkspaceAccessDeniedError(cmd.actor_id, cmd.workspace_id, "add member")

            agg.add_or_update_member(cmd.user_id, role)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_member_added(
                    workspace_id=str(agg.id),
                    user_id=cmd.user_id,
                    role=role.value,
                )
            )
            await tx.commit()
            member = agg.members[cmd.user_id]
            return _to_member_view(member, str(agg.id))

    async def remove_member(self, cmd: RemoveWorkspaceMember) -> bool:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            actor = agg.members.get(cmd.actor_id)
            if not actor or not actor.role.can_admin:
                raise WorkspaceAccessDeniedError(cmd.actor_id, cmd.workspace_id, "remove member")

            agg.remove_member(cmd.user_id)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_member_removed(
                    workspace_id=str(agg.id),
                    user_id=cmd.user_id,
                )
            )
            await tx.commit()
            return True

    async def bind_project(self, cmd: BindProjectToWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            agg.bind_project(cmd.project_id)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_project_bound(
                    workspace_id=str(agg.id),
                    project_id=cmd.project_id,
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def unbind_project(self, cmd: UnbindProjectFromWorkspace) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            agg.unbind_project(cmd.project_id)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_project_unbound(
                    workspace_id=str(agg.id),
                    project_id=cmd.project_id,
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def acquire_lock(self, cmd: AcquireWorkspaceLock) -> WorkspaceLockView:
        lock_id = f"lck_{uuid.uuid4().hex[:10]}"
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=cmd.ttl_seconds)
            if cmd.ttl_seconds
            else None
        )
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            lock = agg.acquire_lock(
                lock_id=lock_id,
                resource_type=cmd.resource_type,
                resource_id=cmd.resource_id,
                holder_id=cmd.holder_id,
                expires_at=expires_at,
            )
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_lock_acquired(
                    workspace_id=str(agg.id),
                    lock_id=lock.lock_id,
                    resource_id=lock.resource_id,
                    holder_id=lock.holder_id,
                    fencing_token=lock.fencing_token,
                )
            )
            await tx.commit()
            return _to_lock_view(lock)

    async def release_lock(self, cmd: ReleaseWorkspaceLock) -> bool:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            agg.release_lock(cmd.resource_id, cmd.holder_id)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_lock_released(
                    workspace_id=str(agg.id),
                    resource_id=cmd.resource_id,
                    holder_id=cmd.holder_id,
                )
            )
            await tx.commit()
            return True

    async def update_quota(self, cmd: UpdateWorkspaceQuota) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            new_quota = WorkspaceQuota(
                max_projects=cmd.max_projects if cmd.max_projects is not None else agg.quota.max_projects,
                max_storage_bytes=cmd.max_storage_bytes if cmd.max_storage_bytes is not None else agg.quota.max_storage_bytes,
                max_concurrent_runs=cmd.max_concurrent_runs if cmd.max_concurrent_runs is not None else agg.quota.max_concurrent_runs,
                max_credits_per_month=cmd.max_credits_per_month if cmd.max_credits_per_month is not None else agg.quota.max_credits_per_month,
            )
            agg.update_quota(new_quota)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_updated(
                    str(agg.id), agg.optimistic_version, name=agg.name
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def update_policy(self, cmd: UpdateWorkspacePolicy) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            new_policy = WorkspacePolicy(
                allowed_runtimes=cmd.allowed_runtimes if cmd.allowed_runtimes is not None else agg.policy.allowed_runtimes,
                sandbox_mode=cmd.sandbox_mode if cmd.sandbox_mode is not None else agg.policy.sandbox_mode,
                require_approvals=cmd.require_approvals if cmd.require_approvals is not None else agg.policy.require_approvals,
                allow_shell=cmd.allow_shell if cmd.allow_shell is not None else agg.policy.allow_shell,
                allow_network=cmd.allow_network if cmd.allow_network is not None else agg.policy.allow_network,
            )
            agg.update_policy(new_policy)
            await tx.store.save(agg)
            tx.record_event(
                workspace_events.workspace_updated(
                    str(agg.id), agg.optimistic_version, name=agg.name
                )
            )
            await tx.commit()
            return _to_view(agg)

    async def create_snapshot(self, cmd: CreateWorkspaceSnapshot) -> WorkspaceSnapshotView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            snapshot = agg.to_snapshot()
            await tx.store.save_snapshot(snapshot)
            await tx.commit()
            return _to_snapshot_view(snapshot)

    async def recalculate_quota(self, cmd: RecalculateWorkspaceQuota) -> WorkspaceView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(cmd.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(cmd.workspace_id)

            agg.update_usage()
            await tx.store.save(agg)
            await tx.commit()
            return _to_view(agg)

    # ----------------------------------------------------------------------- #
    # Query Handlers
    # ----------------------------------------------------------------------- #

    async def get_workspace(self, q: GetWorkspace) -> WorkspaceView | None:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(q.workspace_id)
            return _to_view(agg) if agg else None

    async def get_workspace_by_slug(self, q: GetWorkspaceBySlug) -> WorkspaceView | None:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_slug(q.slug)
            return _to_view(agg) if agg else None

    async def list_workspaces(self, q: ListWorkspaces) -> list[WorkspaceView]:
        async with self._tx_factory() as tx:
            aggs = await tx.store.list_workspaces(
                owner_id=q.owner_id,
                status=q.status,
                limit=q.limit,
                offset=q.offset,
            )
            return [_to_view(a) for a in aggs]

    async def get_members(self, q: GetWorkspaceMembers) -> list[WorkspaceMemberView]:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(q.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(q.workspace_id)
            return [_to_member_view(m, str(agg.id)) for m in agg.members.values()]

    async def get_snapshot(self, q: GetWorkspaceSnapshot) -> WorkspaceSnapshotView | None:
        async with self._tx_factory() as tx:
            snap = await tx.store.get_latest_snapshot(q.workspace_id)
            if snap:
                return _to_snapshot_view(snap)
            agg = await tx.store.get_by_id(q.workspace_id)
            if agg:
                return _to_snapshot_view(agg.to_snapshot())
            return None

    async def list_locks(self, q: ListWorkspaceLocks) -> list[WorkspaceLockView]:
        async with self._tx_factory() as tx:
            locks = await tx.store.list_locks(q.workspace_id)
            return [_to_lock_view(lock) for lock in locks]

    async def validate_path(self, q: ValidateWorkspacePath) -> PathValidationView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(q.workspace_id)
            if agg is None:
                raise WorkspaceNotFoundError(q.workspace_id)

            sandbox = WorkspaceSandbox(agg.root_path)
            try:
                resolved = sandbox.validate_path(q.target_path)
                rel = sandbox.relative_to_root(q.target_path)
                return PathValidationView(
                    workspace_id=q.workspace_id,
                    valid=True,
                    resolved_path=str(resolved),
                    relative_path=rel,
                    error=None,
                )
            except WorkspacePathViolationError as exc:
                return PathValidationView(
                    workspace_id=q.workspace_id,
                    valid=False,
                    resolved_path="",
                    relative_path="",
                    error=str(exc),
                )

    async def check_access(self, q: CheckWorkspaceAccess) -> bool:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_by_id(q.workspace_id)
            if agg is None:
                return False
            member = agg.members.get(q.user_id)
            if not member:
                return False
            req_role = WorkspaceRole(q.required_role) if q.required_role in WorkspaceRole.__members__ else WorkspaceRole.VIEWER
            if req_role == WorkspaceRole.OWNER:
                return bool(member.role == WorkspaceRole.OWNER)
            if req_role == WorkspaceRole.ADMIN:
                return bool(member.role.can_admin)
            if req_role == WorkspaceRole.MEMBER:
                return bool(member.role.can_write)
            return True
