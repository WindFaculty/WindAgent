"""Domain errors for the Workspace bounded context."""

from __future__ import annotations

from windagent.kernel.errors import DomainError


class WorkspaceError(DomainError):
    """Base error for all workspace domain failures."""


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when a workspace cannot be located by ID or slug."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Workspace not found: {identifier}")
        self.identifier = identifier


class WorkspaceSlugAlreadyExistsError(WorkspaceError):
    """Raised when attempting to create or update a workspace with an existing slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Workspace slug already in use: {slug}")
        self.slug = slug


class WorkspaceAccessDeniedError(WorkspaceError):
    """Raised when an actor lacks permission to access or modify a workspace."""

    def __init__(self, user_id: str, workspace_id: str, action: str) -> None:
        super().__init__(f"User '{user_id}' denied '{action}' on workspace '{workspace_id}'")
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.action = action


class WorkspaceQuotaExceededError(WorkspaceError):
    """Raised when a workspace operation exceeds allocated quotas."""

    def __init__(self, workspace_id: str, resource: str, limit: int, current: int) -> None:
        super().__init__(
            f"Workspace '{workspace_id}' exceeded quota for '{resource}': limit={limit}, current={current}"
        )
        self.workspace_id = workspace_id
        self.resource = resource
        self.limit = limit
        self.current = current


class WorkspacePathViolationError(WorkspaceError):
    """Raised when a directory or file path escapes the workspace root boundary."""

    def __init__(self, path: str, root: str, reason: str) -> None:
        super().__init__(f"Path violation for '{path}' against root '{root}': {reason}")
        self.path = path
        self.root = root
        self.reason = reason


class WorkspaceLockConflictError(WorkspaceError):
    """Raised when a distributed workspace/resource lock cannot be acquired."""

    def __init__(self, resource_id: str, current_holder: str) -> None:
        super().__init__(
            f"Lock conflict on resource '{resource_id}': currently held by '{current_holder}'"
        )
        self.resource_id = resource_id
        self.current_holder = current_holder


class WorkspaceStaleVersionError(WorkspaceError):
    """Raised on optimistic concurrency version mismatch during workspace update."""

    def __init__(self, workspace_id: str, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"Stale workspace update on '{workspace_id}': expected version {expected_version}, got {actual_version}"
        )
        self.workspace_id = workspace_id
        self.expected_version = expected_version
        self.actual_version = actual_version


class InvalidWorkspaceStateTransitionError(WorkspaceError):
    """Raised when attempting an invalid status transition on a workspace."""

    def __init__(self, workspace_id: str, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Cannot transition workspace '{workspace_id}' from '{from_state}' to '{to_state}'"
        )
        self.workspace_id = workspace_id
        self.from_state = from_state
        self.to_state = to_state
