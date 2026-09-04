# Phase Workspace: Workspace Management & Sandboxing

**Status**: COMPLETED  
**Date**: 2026-09-02  
**Module**: `windagent.modules.workspace`  
**Milestone**: Milestone 3 (WindAgent Product)

---

## 1. Executive Summary

Phase Workspace delivers multi-tenant workspace isolation, hierarchical membership RBAC, resource quotas, distributed resource locking with fencing tokens, immutable state snapshots, and strict path-containment sandboxing for WindAgent V2.

All implementations strictly adhere to the V2 DDD/Clean Architecture pattern with zero legacy imports and PostgreSQL-ready schemas.

---

## 2. Capabilities & Architecture

### Domain Layer (`windagent.modules.workspace.domain`)
- **Aggregates & Enums**: `WorkspaceAggregate`, `WorkspaceStatus` (`ACTIVE`, `SUSPENDED`, `ARCHIVED`), `WorkspaceTier` (`FREE`, `PRO`, `ENTERPRISE`), `WorkspaceRole` (`OWNER`, `ADMIN`, `MEMBER`, `VIEWER`).
- **Quota & Policies**: `WorkspaceQuota` (projects, storage, concurrency, monthly credits), `WorkspaceQuotaUsage`, `WorkspacePolicy` (allowed runtimes, sandbox modes, approval gates, shell & network control).
- **Resource Locking**: `WorkspaceLock` with monotonic fencing tokens and TTL expiration for concurrency conflict prevention.
- **Sandboxing**: `WorkspaceSandbox` enforcing canonical path resolution, null-byte rejection, and path traversal (`..`) escape prevention.
- **Snapshots**: Immutable `WorkspaceSnapshot` capturing point-in-time state.

### Application Layer (`windagent.modules.workspace.application`)
- **Commands**: 15 distinct command contracts (`CreateWorkspace`, `UpdateWorkspace`, `ArchiveWorkspace`, `SuspendWorkspace`, `RestoreWorkspace`, `AddWorkspaceMember`, `RemoveWorkspaceMember`, `BindProjectToWorkspace`, `UnbindProjectFromWorkspace`, `AcquireWorkspaceLock`, `ReleaseWorkspaceLock`, `UpdateWorkspaceQuota`, `UpdateWorkspacePolicy`, `CreateWorkspaceSnapshot`, `RecalculateWorkspaceQuota`).
- **Queries**: 8 query contracts (`GetWorkspace`, `GetWorkspaceBySlug`, `ListWorkspaces`, `GetWorkspaceMembers`, `ListWorkspaceLocks`, `GetWorkspaceSnapshot`, `ValidateWorkspacePath`, `GetWorkspaceUsage`).
- **Events**: Integration outbox events (`workspace.created`, `workspace.archived`, `workspace.member.added`, `workspace.member.removed`, `workspace.lock.acquired`, `workspace.lock.released`).
- **Handlers**: CQRS command and query dispatch handlers.

### Infrastructure Layer (`windagent.modules.workspace.infrastructure`)
- **Storage**: `SqlWorkspaceStore` (SQLAlchemy async) and `InMemoryWorkspaceStore`.
- **Database Tables**:
  - `workspaces`: Core workspace entity metadata, status, tier, optimistic versioning.
  - `workspace_members`: User membership and RBAC role bindings.
  - `workspace_project_bindings`: Many-to-many project associations.
  - `workspace_locks`: Distributed resource locks with fencing tokens and expiration.
  - `workspace_snapshots`: Historical point-in-time audit snapshots.
- **Migration**: `migrations/versions/0012_workspace.py`.

### Background Jobs (`windagent.modules.workspace.jobs`)
- `workspace.quota.recalculate`: Recalculates storage, project counts, and credit usage.
- `workspace.cleanup.archived`: Cleans up expired locks and purges retention-expired archived resources.

### API Layer (`windagent.modules.workspace.api`)
- REST routes mounted at `/api/v4/workspaces`:
  - `POST /api/v4/workspaces`
  - `GET /api/v4/workspaces`
  - `GET /api/v4/workspaces/{id_or_slug}`
  - `PATCH /api/v4/workspaces/{workspace_id}`
  - `POST /api/v4/workspaces/{workspace_id}/archive`
  - `POST /api/v4/workspaces/{workspace_id}/suspend`
  - `POST /api/v4/workspaces/{workspace_id}/restore`
  - `POST /api/v4/workspaces/{workspace_id}/members`
  - `GET /api/v4/workspaces/{workspace_id}/members`
  - `DELETE /api/v4/workspaces/{workspace_id}/members/{user_id}`
  - `POST /api/v4/workspaces/{workspace_id}/projects/{project_id}`
  - `DELETE /api/v4/workspaces/{workspace_id}/projects/{project_id}`
  - `POST /api/v4/workspaces/{workspace_id}/locks`
  - `GET /api/v4/workspaces/{workspace_id}/locks`
  - `DELETE /api/v4/workspaces/{workspace_id}/locks/{resource_id}`
  - `GET /api/v4/workspaces/{workspace_id}/snapshot`
  - `POST /api/v4/workspaces/{workspace_id}/validate-path`

---

## 3. Verification & Quality

- **Unit Tests**:
  - `tests/unit/test_workspace_domain.py`: Domain invariants, quota limits, member RBAC, lock conflict & fencing tokens, sandbox path containment.
  - `tests/unit/test_workspace_services.py`: Service orchestration, transactions, locking, quota enforcement.
  - `tests/unit/test_workspace_api.py`: Manifest discovery, REST CRUD, membership, lock lifecycle.
- **Coverage**: 100% test pass rate across all workspace test suites.
