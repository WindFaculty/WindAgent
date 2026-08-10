"""
Screenplay Command Handlers (Stage C — UI10 & UI14).

Handles mutating structured screenplay commands, revision creation, and revision locking.
Enforces revision immutability invariants: mutations against a LOCKED revision fail with REJECTED_LOCKED.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from windagent_core.contracts.video_production.video_production_uow import (
    VideoProductionUnitOfWorkPort,
)


class ScreenplayCommandHandler:
    """Command handler processing structured screenplay mutation requests."""

    def __init__(self, uow: VideoProductionUnitOfWorkPort) -> None:
        self.uow = uow

    async def handle_command(
        self,
        command_type: str,
        project_id: str,
        target_revision_id: str,
        payload: Dict[str, Any],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """Dispatch structured command to appropriate domain operation."""
        project = await self.uow.projects.get_project(project_id)
        if not project:
            return {
                "status": "FAILED",
                "message": f"Project '{project_id}' not found.",
                "updated_revision_id": target_revision_id,
            }

        active_rev_id = project.get("active_revision_id", target_revision_id)
        if target_revision_id != active_rev_id:
            return {
                "status": "REJECTED_STALE",
                "message": f"Target revision '{target_revision_id}' is stale. Server is at '{active_rev_id}'.",
                "updated_revision_id": active_rev_id,
            }

        # Check revision lock status
        rev_record = await self.uow.projects.get_revision(target_revision_id)
        rev_status = (rev_record or {}).get("status", "DRAFT")
        if rev_status == "LOCKED" and command_type not in ("CREATE_REVISION", "UNLOCK_REVISION"):
            return {
                "status": "REJECTED_LOCKED",
                "message": f"Revision '{target_revision_id}' is LOCKED and immutable. Create a new draft revision to edit.",
                "updated_revision_id": target_revision_id,
            }

        # Handle commands
        if command_type == "CREATE_REVISION":
            return await self._create_revision(project_id, target_revision_id, payload)
        elif command_type == "LOCK_REVISION":
            return await self._lock_revision(project_id, target_revision_id, payload)
        elif command_type in ("UPDATE_SCENE", "ADD_SCENE", "DELETE_SCENE", "REORDER_SCENES", "SPLIT_SCENE", "MERGE_SCENE"):
            return await self._mutate_scene(command_type, project_id, target_revision_id, payload)
        elif command_type in ("ADD_DIALOGUE", "UPDATE_DIALOGUE", "DELETE_DIALOGUE"):
            return await self._mutate_dialogue(command_type, project_id, target_revision_id, payload)
        else:
            return {
                "status": "COMPLETED",
                "message": f"Command '{command_type}' acknowledged.",
                "updated_revision_id": target_revision_id,
            }

    async def _create_revision(
        self, project_id: str, parent_revision_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new DRAFT revision branched from parent revision (UI14)."""
        new_rev_id = f"rev_{uuid.uuid4().hex[:8]}"
        seq = (await self.uow.events.get_max_sequence(project_id) or 0) + 1

        await self.uow.projects.save_revision(
            revision_id=new_rev_id,
            project_id=project_id,
            parent_revision_id=parent_revision_id,
            status="DRAFT",
            content_hash=f"hash_{uuid.uuid4().hex[:12]}",
            sequence=seq,
        )
        await self.uow.projects.save_project(
            project_id=project_id,
            name=payload.get("name", "Production Workspace"),
            status="ACTIVE",
            active_revision_id=new_rev_id,
        )
        await self.uow.events.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            sequence=seq,
            project_id=project_id,
            revision_id=new_rev_id,
            event_type="REVISION_CREATED",
            aggregate_type="REVISION",
            aggregate_id=new_rev_id,
            payload={"parent_revision_id": parent_revision_id, "reason": payload.get("reason", "Draft editing")},
        )
        await self.uow.commit()

        return {
            "status": "COMPLETED",
            "message": f"Created new DRAFT revision '{new_rev_id}' derived from '{parent_revision_id}'.",
            "updated_revision_id": new_rev_id,
            "current_sequence": seq,
        }

    async def _lock_revision(
        self, project_id: str, revision_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Lock current revision after validation checks pass (UI14 & UI18)."""
        seq = (await self.uow.events.get_max_sequence(project_id) or 0) + 1

        await self.uow.projects.save_revision(
            revision_id=revision_id,
            project_id=project_id,
            parent_revision_id=payload.get("parent_revision_id"),
            status="LOCKED",
            content_hash=f"hash_locked_{uuid.uuid4().hex[:8]}",
            sequence=seq,
        )
        await self.uow.events.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            sequence=seq,
            project_id=project_id,
            revision_id=revision_id,
            event_type="REVISION_LOCKED",
            aggregate_type="REVISION",
            aggregate_id=revision_id,
            payload={"actor": payload.get("actor", "user"), "reason": payload.get("reason", "Approved screenplay lock")},
        )
        await self.uow.commit()

        return {
            "status": "COMPLETED",
            "message": f"Revision '{revision_id}' is now LOCKED and immutable.",
            "updated_revision_id": revision_id,
            "current_sequence": seq,
        }

    async def _mutate_scene(
        self, command_type: str, project_id: str, revision_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle scene level mutations."""
        seq = (await self.uow.events.get_max_sequence(project_id) or 0) + 1

        await self.uow.events.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            sequence=seq,
            project_id=project_id,
            revision_id=revision_id,
            event_type=f"SCENE_{command_type}",
            aggregate_type="SCENE",
            aggregate_id=payload.get("scene_id", f"scene_{uuid.uuid4().hex[:6]}"),
            payload=payload,
        )
        await self.uow.commit()

        return {
            "status": "COMPLETED",
            "message": f"Scene action '{command_type}' applied successfully.",
            "updated_revision_id": revision_id,
            "current_sequence": seq,
            "payload": payload,
        }

    async def _mutate_dialogue(
        self, command_type: str, project_id: str, revision_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle dialogue level mutations."""
        seq = (await self.uow.events.get_max_sequence(project_id) or 0) + 1

        await self.uow.events.append_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            sequence=seq,
            project_id=project_id,
            revision_id=revision_id,
            event_type=f"DIALOGUE_{command_type}",
            aggregate_type="DIALOGUE",
            aggregate_id=payload.get("dialogue_id", f"dlg_{uuid.uuid4().hex[:6]}"),
            payload=payload,
        )
        await self.uow.commit()

        return {
            "status": "COMPLETED",
            "message": f"Dialogue action '{command_type}' applied successfully.",
            "updated_revision_id": revision_id,
            "current_sequence": seq,
            "payload": payload,
        }
