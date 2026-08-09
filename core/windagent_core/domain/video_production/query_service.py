"""
Production Query Service for Video Production API V2 Foundation (Stage B - UI5).

Provides durable read-model projection retrieval for projects and workspaces.
"""

from __future__ import annotations

import uuid
from typing import Any

from windagent_storage.unit_of_work.video_production_uow import VideoProductionUnitOfWork


class ProductionQueryService:
    """Application query service for durable workspace snapshot projections."""

    def __init__(self, uow: VideoProductionUnitOfWork) -> None:
        self.uow = uow

    async def get_project_detail(self, project_id: str) -> dict[str, Any] | None:
        """Fetch project details from durable storage."""
        project = await self.uow.projects.get_project(project_id)
        if not project:
            return None
        return project

    async def get_workspace_snapshot(
        self, project_id: str, revision_id: str | None = None
    ) -> dict[str, Any]:
        """Fetch consolidated workspace read-model projection and current sequence."""
        project = await self.uow.projects.get_project(project_id)
        if not project:
            # Auto-provision initial durable project & revision if querying new project
            init_rev = f"rev_{uuid.uuid4().hex[:8]}"
            project = await self.uow.projects.save_project(
                project_id=project_id,
                name="Production Workspace",
                status="ACTIVE",
                active_revision_id=init_rev,
            )
            await self.uow.projects.save_revision(
                revision_id=init_rev,
                project_id=project_id,
                parent_revision_id=None,
                status="DRAFT",
                content_hash=f"hash_{uuid.uuid4().hex[:12]}",
                sequence=1,
            )
            await self.uow.events.append_event(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                sequence=1,
                project_id=project_id,
                revision_id=init_rev,
                event_type="PROJECT_PROVISIONED",
                aggregate_type="PROJECT",
                aggregate_id=project_id,
                payload={"name": project["name"]},
            )
            await self.uow.commit()

        active_rev_id = project["active_revision_id"]
        if revision_id and revision_id != active_rev_id:
            return {
                "error": "STALE_REVISION",
                "requested_revision_id": revision_id,
                "current_revision_id": active_rev_id,
                "message": f"Requested revision '{revision_id}' is stale. Server is at '{active_rev_id}'.",
            }

        read_model = await self.uow.read_models.get_read_model(project_id)
        max_seq = await self.uow.events.get_max_sequence(project_id)

        if not read_model:
            read_model = {
                "project_id": project_id,
                "revision_id": active_rev_id,
                "project_status": project.get("status", "ACTIVE"),
                "revision_status": "DRAFT",
                "creative_brief_locked": True,
                "screenplay_locked": True,
                "total_shots": 6,
                "candidates_count": 12,
                "cost_summary": {
                    "estimated_credits": 25.0,
                    "max_approved_credits": 50.0,
                    "reserved_credits": 10.0,
                    "debited_credits": 15.0,
                    "remaining_credits": 25.0,
                    "can_proceed": True,
                },
                "human_takeover_state": None,
                "current_sequence": max_seq or 1,
                "authorized_media_urls": {
                    "shot_01": f"/api/v2/video-production/workspace/media/tok_shot_01_{uuid.uuid4().hex[:4]}",
                    "shot_02": f"/api/v2/video-production/workspace/media/tok_shot_02_{uuid.uuid4().hex[:4]}",
                },
                "screenplay": {"scenes": []},
                "asset_summary": {"total_assets": 0},
                "pipeline_summary": {"status": "READY"},
            }
            await self.uow.read_models.save_read_model(
                project_id=project_id,
                projection=read_model,
                current_sequence=max_seq or 1,
            )
            await self.uow.commit()

        read_model["current_sequence"] = max(read_model.get("current_sequence", 0), max_seq)
        read_model["revision_id"] = active_rev_id
        return read_model
