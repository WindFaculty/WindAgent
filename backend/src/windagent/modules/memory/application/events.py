"""Outbox event factory for the Memory bounded context (Phase 14)."""

import uuid

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types import Version


def _eid(value: str) -> EntityId:
    try:
        return EntityId(value)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"memory.{value}"))


class MemoryEventFactory:
    """Creates canonical memory.* event envelopes."""

    def memory_created(
        self,
        memory_id: str,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="memory.created",
            aggregate_type="memory_record",
            aggregate_id=_eid(memory_id),
            sequence=0,
            payload={
                "memory_id": memory_id,
                "scope": scope,
                "key": key,
                "project_id": project_id,
                "session_id": session_id,
            },
            event_version=Version(1),
        )

    def memory_updated(
        self,
        memory_id: str,
        scope: str,
        key: str,
        version: int,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="memory.updated",
            aggregate_type="memory_record",
            aggregate_id=_eid(memory_id),
            sequence=0,
            payload={
                "memory_id": memory_id,
                "scope": scope,
                "key": key,
                "version": version,
                "project_id": project_id,
                "session_id": session_id,
            },
            event_version=Version(1),
        )

    def memory_deleted(
        self,
        memory_id: str,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="memory.deleted",
            aggregate_type="memory_record",
            aggregate_id=_eid(memory_id),
            sequence=0,
            payload={
                "memory_id": memory_id,
                "scope": scope,
                "key": key,
                "project_id": project_id,
                "session_id": session_id,
            },
            event_version=Version(1),
        )

    def memory_superseded(
        self,
        memory_id: str,
        superseded_by_id: str,
        scope: str,
        key: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="memory.superseded",
            aggregate_type="memory_record",
            aggregate_id=_eid(memory_id),
            sequence=0,
            payload={
                "memory_id": memory_id,
                "superseded_by_id": superseded_by_id,
                "scope": scope,
                "key": key,
            },
            event_version=Version(1),
        )

    def memory_evicted(
        self,
        count: int,
        scope: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="memory.evicted",
            aggregate_type="memory_module",
            aggregate_id=_eid("memory_system"),
            sequence=0,
            payload={
                "count": count,
                "scope": scope,
            },
            event_version=Version(1),
        )


memory_events = MemoryEventFactory()
