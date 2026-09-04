"""SQL adapter for the Workspace store."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.ports import TransactionScope, WorkspaceStore
from ..domain.errors import WorkspaceStaleVersionError
from ..domain.models import (
    WorkspaceAggregate,
    WorkspaceLock,
    WorkspaceMember,
    WorkspacePolicy,
    WorkspaceQuota,
    WorkspaceQuotaUsage,
    WorkspaceRole,
    WorkspaceSnapshot,
    WorkspaceStatus,
    WorkspaceTier,
)
from .tables import (
    workspace_locks_table,
    workspace_members_table,
    workspace_project_bindings_table,
    workspace_snapshots_table,
    workspaces_table,
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class SqlWorkspaceStore(WorkspaceStore):
    """SQLAlchemy implementation of WorkspaceStore."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: str) -> WorkspaceAggregate | None:
        stmt = select(workspaces_table).where(workspaces_table.c.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return await self._hydrate_aggregate(row)

    async def get_by_slug(self, slug: str) -> WorkspaceAggregate | None:
        stmt = select(workspaces_table).where(workspaces_table.c.slug == slug)
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return await self._hydrate_aggregate(row)

    async def list_workspaces(
        self,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkspaceAggregate]:
        stmt = select(workspaces_table)
        if owner_id:
            stmt = stmt.where(workspaces_table.c.owner_id == owner_id)
        if status:
            stmt = stmt.where(workspaces_table.c.status == status)
        stmt = stmt.limit(limit).offset(offset).order_by(workspaces_table.c.created_at.desc())

        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [await self._hydrate_aggregate(row) for row in rows]

    async def save(self, aggregate: WorkspaceAggregate, expected_version: int | None = None) -> None:
        ws_id = str(aggregate.id)
        existing_stmt = select(workspaces_table.c.optimistic_version).where(
            workspaces_table.c.workspace_id == ws_id
        )
        existing_res = await self._session.execute(existing_stmt)
        existing_row = existing_res.first()

        quota_dict = {
            "max_projects": aggregate.quota.max_projects,
            "max_storage_bytes": aggregate.quota.max_storage_bytes,
            "max_concurrent_runs": aggregate.quota.max_concurrent_runs,
            "max_credits_per_month": aggregate.quota.max_credits_per_month,
        }
        usage_dict = {
            "current_projects": aggregate.quota_usage.current_projects,
            "current_storage_bytes": aggregate.quota_usage.current_storage_bytes,
            "current_concurrent_runs": aggregate.quota_usage.current_concurrent_runs,
            "used_credits": aggregate.quota_usage.used_credits,
        }
        policy_dict = {
            "allowed_runtimes": list(aggregate.policy.allowed_runtimes),
            "sandbox_mode": aggregate.policy.sandbox_mode,
            "require_approvals": aggregate.policy.require_approvals,
            "allow_shell": aggregate.policy.allow_shell,
            "allow_network": aggregate.policy.allow_network,
        }

        if existing_row is None:
            # Insert workspace
            ins = insert(workspaces_table).values(
                workspace_id=ws_id,
                name=aggregate.name,
                slug=aggregate.slug,
                root_path=aggregate.root_path,
                owner_id=aggregate.owner_id,
                description=aggregate.description,
                status=aggregate.status.value,
                tier=aggregate.tier.value,
                quota_json=_dump(quota_dict),
                quota_usage_json=_dump(usage_dict),
                policy_json=_dump(policy_dict),
                metadata_json=_dump(aggregate.metadata),
                optimistic_version=aggregate.optimistic_version,
                created_at=aggregate.created_at,
                updated_at=aggregate.updated_at,
            )
            await self._session.execute(ins)
        else:
            cur_ver = existing_row[0]
            if expected_version is not None and cur_ver != expected_version:
                raise WorkspaceStaleVersionError(ws_id, expected_version, cur_ver)

            upd = (
                update(workspaces_table)
                .where(workspaces_table.c.workspace_id == ws_id)
                .values(
                    name=aggregate.name,
                    slug=aggregate.slug,
                    root_path=aggregate.root_path,
                    description=aggregate.description,
                    status=aggregate.status.value,
                    tier=aggregate.tier.value,
                    quota_json=_dump(quota_dict),
                    quota_usage_json=_dump(usage_dict),
                    policy_json=_dump(policy_dict),
                    metadata_json=_dump(aggregate.metadata),
                    optimistic_version=aggregate.optimistic_version,
                    updated_at=aggregate.updated_at,
                )
            )
            if expected_version is not None:
                upd = upd.where(workspaces_table.c.optimistic_version == expected_version)
            res = await self._session.execute(upd)
            if expected_version is not None and getattr(res, "rowcount", 0) == 0:
                raise WorkspaceStaleVersionError(ws_id, expected_version, cur_ver)

        # Sync members
        await self._session.execute(
            delete(workspace_members_table).where(workspace_members_table.c.workspace_id == ws_id)
        )
        if aggregate.members:
            member_values = [
                {
                    "workspace_id": ws_id,
                    "user_id": m.user_id,
                    "role": m.role.value,
                    "joined_at": m.joined_at,
                }
                for m in aggregate.members.values()
            ]
            await self._session.execute(insert(workspace_members_table).values(member_values))

        # Sync project bindings
        await self._session.execute(
            delete(workspace_project_bindings_table).where(
                workspace_project_bindings_table.c.workspace_id == ws_id
            )
        )
        if aggregate.bound_project_ids:
            binding_values = [
                {
                    "workspace_id": ws_id,
                    "project_id": pid,
                    "bound_at": aggregate.updated_at,
                }
                for pid in aggregate.bound_project_ids
            ]
            await self._session.execute(insert(workspace_project_bindings_table).values(binding_values))

        # Sync locks
        await self._session.execute(
            delete(workspace_locks_table).where(workspace_locks_table.c.workspace_id == ws_id)
        )
        if aggregate.locks:
            lock_values = [
                {
                    "lock_id": lk.lock_id,
                    "workspace_id": ws_id,
                    "resource_type": lk.resource_type,
                    "resource_id": lk.resource_id,
                    "holder_id": lk.holder_id,
                    "acquired_at": lk.acquired_at,
                    "expires_at": lk.expires_at,
                    "fencing_token": lk.fencing_token,
                }
                for lk in aggregate.locks.values()
            ]
            await self._session.execute(insert(workspace_locks_table).values(lock_values))

    async def delete(self, workspace_id: str) -> bool:
        stmt = delete(workspaces_table).where(workspaces_table.c.workspace_id == workspace_id)
        res = await self._session.execute(stmt)
        return bool(getattr(res, "rowcount", 0) > 0)

    async def save_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        snap_id = f"snp_{uuid.uuid4().hex[:12]}"
        data_dict = {
            "workspace_id": snapshot.workspace_id,
            "name": snapshot.name,
            "slug": snapshot.slug,
            "status": snapshot.status.value,
            "tier": snapshot.tier.value,
            "owner_id": snapshot.owner_id,
            "root_path": snapshot.root_path,
            "members_count": snapshot.members_count,
            "projects_count": snapshot.projects_count,
            "quota": {
                "max_projects": snapshot.quota.max_projects,
                "max_storage_bytes": snapshot.quota.max_storage_bytes,
                "max_concurrent_runs": snapshot.quota.max_concurrent_runs,
                "max_credits_per_month": snapshot.quota.max_credits_per_month,
            },
            "quota_usage": {
                "current_projects": snapshot.quota_usage.current_projects,
                "current_storage_bytes": snapshot.quota_usage.current_storage_bytes,
                "current_concurrent_runs": snapshot.quota_usage.current_concurrent_runs,
                "used_credits": snapshot.quota_usage.used_credits,
            },
            "policy": {
                "allowed_runtimes": list(snapshot.policy.allowed_runtimes),
                "sandbox_mode": snapshot.policy.sandbox_mode,
                "require_approvals": snapshot.policy.require_approvals,
                "allow_shell": snapshot.policy.allow_shell,
                "allow_network": snapshot.policy.allow_network,
            },
            "optimistic_version": snapshot.optimistic_version,
            "created_at": snapshot.created_at.isoformat(),
            "updated_at": snapshot.updated_at.isoformat(),
        }
        ins = insert(workspace_snapshots_table).values(
            snapshot_id=snap_id,
            workspace_id=snapshot.workspace_id,
            data_json=_dump(data_dict),
            created_at=datetime.now(UTC),
        )
        await self._session.execute(ins)

    async def get_latest_snapshot(self, workspace_id: str) -> WorkspaceSnapshot | None:
        stmt = (
            select(workspace_snapshots_table)
            .where(workspace_snapshots_table.c.workspace_id == workspace_id)
            .order_by(workspace_snapshots_table.c.created_at.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        row = res.mappings().first()
        if not row:
            return None
        data = json.loads(row["data_json"])
        return WorkspaceSnapshot(
            workspace_id=data["workspace_id"],
            name=data["name"],
            slug=data["slug"],
            status=WorkspaceStatus(data["status"]),
            tier=WorkspaceTier(data["tier"]),
            owner_id=data["owner_id"],
            root_path=data["root_path"],
            members_count=data["members_count"],
            projects_count=data["projects_count"],
            quota=WorkspaceQuota(**data["quota"]),
            quota_usage=WorkspaceQuotaUsage(**data["quota_usage"]),
            policy=WorkspacePolicy(**data["policy"]),
            optimistic_version=data["optimistic_version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def list_locks(self, workspace_id: str) -> list[WorkspaceLock]:
        stmt = select(workspace_locks_table).where(workspace_locks_table.c.workspace_id == workspace_id)
        res = await self._session.execute(stmt)
        rows = res.mappings().all()
        return [
            WorkspaceLock(
                lock_id=r["lock_id"],
                workspace_id=r["workspace_id"],
                resource_type=r["resource_type"],
                resource_id=r["resource_id"],
                holder_id=r["holder_id"],
                acquired_at=_as_utc(r["acquired_at"]) or datetime.now(UTC),
                expires_at=_as_utc(r["expires_at"]),
                fencing_token=r["fencing_token"],
            )
            for r in rows
        ]

    async def _hydrate_aggregate(self, row: Any) -> WorkspaceAggregate:
        ws_id = row["workspace_id"]
        # Fetch members
        m_stmt = select(workspace_members_table).where(workspace_members_table.c.workspace_id == ws_id)
        m_res = await self._session.execute(m_stmt)
        members = {
            r["user_id"]: WorkspaceMember(
                user_id=r["user_id"],
                role=WorkspaceRole(r["role"]),
                joined_at=_as_utc(r["joined_at"]) or datetime.now(UTC),
            )
            for r in m_res.mappings().all()
        }

        # Fetch bound projects
        p_stmt = select(workspace_project_bindings_table.c.project_id).where(
            workspace_project_bindings_table.c.workspace_id == ws_id
        )
        p_res = await self._session.execute(p_stmt)
        bound_projects = {r[0] for r in p_res.all()}

        # Fetch locks
        l_stmt = select(workspace_locks_table).where(workspace_locks_table.c.workspace_id == ws_id)
        l_res = await self._session.execute(l_stmt)
        locks = {
            r["resource_id"]: WorkspaceLock(
                lock_id=r["lock_id"],
                workspace_id=r["workspace_id"],
                resource_type=r["resource_type"],
                resource_id=r["resource_id"],
                holder_id=r["holder_id"],
                acquired_at=_as_utc(r["acquired_at"]) or datetime.now(UTC),
                expires_at=_as_utc(r["expires_at"]),
                fencing_token=r["fencing_token"],
            )
            for r in l_res.mappings().all()
        }

        quota_data = json.loads(row["quota_json"] or "{}")
        usage_data = json.loads(row["quota_usage_json"] or "{}")
        policy_data = json.loads(row["policy_json"] or "{}")
        metadata_data = json.loads(row["metadata_json"] or "{}")

        return WorkspaceAggregate(
            id=EntityId(ws_id),
            name=row["name"],
            slug=row["slug"],
            root_path=row["root_path"],
            owner_id=row["owner_id"],
            description=row["description"],
            status=WorkspaceStatus(row["status"]),
            tier=WorkspaceTier(row["tier"]),
            quota=WorkspaceQuota(**quota_data),
            quota_usage=WorkspaceQuotaUsage(**usage_data),
            policy=WorkspacePolicy(**policy_data),
            members=members,
            bound_project_ids=bound_projects,
            locks=locks,
            metadata=metadata_data,
            optimistic_version=row["optimistic_version"],
            created_at=_as_utc(row["created_at"]) or datetime.now(UTC),
            updated_at=_as_utc(row["updated_at"]) or datetime.now(UTC),
        )


class SqlTransactionScope(TransactionScope):
    """SQL unit of work transaction scope for Workspace with outbox event recording."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None
        self._events: list[EventEnvelope] = []

    @property
    def store(self) -> WorkspaceStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return SqlWorkspaceStore(self._uow.session)

    def record_event(self, envelope: EventEnvelope) -> None:
        self._events.append(envelope)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        if self._events:
            outbox = TransactionalOutbox(self._uow)
            for env in self._events:
                await outbox.record_next(env)
        await self._uow.commit()

    async def rollback(self) -> None:
        if self._uow is not None:
            await self._uow.rollback()

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):
            raise TypeError("transaction scope requires a SQL unit of work")
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_val, None)
            self._uow = None
        return False


def sql_scope_factory(database: Database) -> Callable[[], TransactionScope]:
    return lambda: SqlTransactionScope(database)


