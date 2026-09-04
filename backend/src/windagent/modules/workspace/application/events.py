"""Outbox event factory for the Workspace bounded context."""

from __future__ import annotations

import uuid

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types import Version


def _eid(value: str) -> EntityId:
    try:
        return EntityId(value)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"workspace.{value}"))


class WorkspaceEventFactory:
    """Produces canonical workspace.* event envelopes."""

    def workspace_created(
        self,
        workspace_id: str,
        slug: str,
        name: str,
        owner_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.created",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "slug": slug,
                "name": name,
                "owner_id": owner_id,
            },
            event_version=Version(1),
        )

    def workspace_updated(
        self,
        workspace_id: str,
        version: int,
        name: str | None = None,
        status: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.updated",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "version": version,
                "name": name,
                "status": status,
            },
            event_version=Version(1),
        )

    def workspace_archived(
        self,
        workspace_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.archived",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={"workspace_id": workspace_id},
            event_version=Version(1),
        )

    def workspace_member_added(
        self,
        workspace_id: str,
        user_id: str,
        role: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.member_added",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "role": role,
            },
            event_version=Version(1),
        )

    def workspace_member_removed(
        self,
        workspace_id: str,
        user_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.member_removed",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "user_id": user_id,
            },
            event_version=Version(1),
        )

    def workspace_project_bound(
        self,
        workspace_id: str,
        project_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.project_bound",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "project_id": project_id,
            },
            event_version=Version(1),
        )

    def workspace_project_unbound(
        self,
        workspace_id: str,
        project_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.project_unbound",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "project_id": project_id,
            },
            event_version=Version(1),
        )

    def workspace_lock_acquired(
        self,
        workspace_id: str,
        lock_id: str,
        resource_id: str,
        holder_id: str,
        fencing_token: int,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.lock_acquired",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "lock_id": lock_id,
                "resource_id": resource_id,
                "holder_id": holder_id,
                "fencing_token": fencing_token,
            },
            event_version=Version(1),
        )

    def workspace_lock_released(
        self,
        workspace_id: str,
        resource_id: str,
        holder_id: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.lock_released",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "resource_id": resource_id,
                "holder_id": holder_id,
            },
            event_version=Version(1),
        )

    def workspace_quota_exceeded(
        self,
        workspace_id: str,
        resource: str,
        limit: int,
        current: int,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="workspace.quota_exceeded",
            aggregate_type="workspace",
            aggregate_id=_eid(workspace_id),
            sequence=0,
            payload={
                "workspace_id": workspace_id,
                "resource": resource,
                "limit": limit,
                "current": current,
            },
            event_version=Version(1),
        )


workspace_events = WorkspaceEventFactory()
