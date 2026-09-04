"""Importer for legacy workspace data into V2 Workspace bounded context."""

from __future__ import annotations

from typing import Any


class WorkspaceImporter:
    """Imports legacy workspaces and team membership into V2 schema."""

    def __init__(self) -> None:
        self.imported_workspaces: list[dict[str, Any]] = []
        self.imported_members: list[dict[str, Any]] = []

    def import_legacy_workspace(self, legacy_data: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Transform and validate legacy workspace schema into V2 aggregate."""
        workspace_id = legacy_data.get("id") or f"ws-{legacy_data['name'].lower().replace(' ', '-')}"
        slug = legacy_data.get("slug") or legacy_data["name"].lower().replace(" ", "-")

        v2_record = {
            "id": workspace_id,
            "name": legacy_data["name"],
            "slug": slug,
            "owner_id": legacy_data.get("owner_id", "user-admin"),
            "status": "active",
            "max_projects": legacy_data.get("quota_projects", 25),
            "max_storage_bytes": legacy_data.get("quota_storage", 50 * 1024 * 1024 * 1024),
            "max_concurrent_runs": legacy_data.get("quota_concurrency", 10),
            "max_credits_per_month": legacy_data.get("quota_credits", 100000),
            "created_at": legacy_data.get("created_at", "2026-09-02T00:00:00Z"),
        }

        if not dry_run:
            self.imported_workspaces.append(v2_record)

        return v2_record

    def import_legacy_members(self, workspace_id: str, legacy_members: list[dict[str, Any]], *, dry_run: bool = False) -> list[dict[str, Any]]:
        """Import workspace members with RBAC role mapping."""
        role_map = {
            "admin": "ADMIN",
            "owner": "OWNER",
            "editor": "MEMBER",
            "viewer": "VIEWER",
        }

        records = []
        for mem in legacy_members:
            role = role_map.get(mem.get("role", "member").lower(), "MEMBER")
            rec = {
                "workspace_id": workspace_id,
                "user_id": mem["user_id"],
                "role": role,
                "joined_at": mem.get("joined_at", "2026-09-02T00:00:00Z"),
            }
            records.append(rec)
            if not dry_run:
                self.imported_members.append(rec)

        return records
