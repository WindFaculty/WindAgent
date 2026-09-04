"""Background job handlers for Workspace."""

from __future__ import annotations

from typing import Any

from ..application.commands import RecalculateWorkspaceQuota
from ..application.runtime import WorkspaceServices, container_for


class WorkspaceQuotaRecalculateJobHandler:
    job_type = "workspace.quota.recalculate"

    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace_id = str(payload.get("workspace_id", ""))
        if not workspace_id:
            return {"status": "FAILED", "error": "missing workspace_id in job payload"}
        try:
            view = await container_for(self._services).workspace.recalculate_quota(
                RecalculateWorkspaceQuota(workspace_id=workspace_id)
            )
            return {"status": "SUCCEEDED", "workspace": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class WorkspaceCleanupArchivedJobHandler:
    job_type = "workspace.cleanup.archived"

    def __init__(self, services: WorkspaceServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "cleaned_count": 0}
