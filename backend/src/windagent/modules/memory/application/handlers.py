"""Command, query, and job handlers for the Memory module (Phase 14)."""

from __future__ import annotations

from .commands import (
    DeleteMemory,
    EvictExpiredMemories,
    ForgetMemory,
    ForgetMemoryByPattern,
    SaveManyMemories,
    SaveMemory,
    SetMemoryTtl,
)
from .models import MemoryRecordView, MemoryStatsView
from .queries import (
    GetMemory,
    GetMemoryById,
    GetMemoryStats,
    ListEpisodicMemories,
    ListMemories,
    ListMemoriesByProject,
    ListMemoriesByScope,
    ListMemoriesBySession,
    ListMemoriesByStatus,
    ListPolicies,
    ListProceduralMemories,
    ListValidatedKnowledge,
    SearchMemoriesByTag,
)
from .runtime import MemoryServices, container_for

# --------------------------------------------------------------------------- #
# Command Handlers
# --------------------------------------------------------------------------- #


class SaveMemoryHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: SaveMemory) -> MemoryRecordView:
        return await container_for(self._services).memory.save_memory(cmd)


class SaveManyMemoriesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: SaveManyMemories) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.save_many(cmd)


class DeleteMemoryHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: DeleteMemory) -> bool:
        return await container_for(self._services).memory.delete_memory(cmd)


class ForgetMemoryHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: ForgetMemory) -> bool:
        return await container_for(self._services).memory.delete_memory(cmd)


class ForgetMemoryByPatternHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: ForgetMemoryByPattern) -> int:
        return await container_for(self._services).memory.forget_by_pattern(cmd)


class SetMemoryTtlHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: SetMemoryTtl) -> bool:
        return await container_for(self._services).memory.set_ttl(cmd)


class EvictExpiredMemoriesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: EvictExpiredMemories) -> int:
        return await container_for(self._services).memory.evict_expired(cmd)


# --------------------------------------------------------------------------- #
# Query Handlers
# --------------------------------------------------------------------------- #


class GetMemoryHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetMemory) -> MemoryRecordView | None:
        return await container_for(self._services).memory.get_memory(
            scope=query.scope,
            key=query.key,
            project_id=query.project_id,
            session_id=query.session_id,
        )


class GetMemoryByIdHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetMemoryById) -> MemoryRecordView | None:
        return await container_for(self._services).memory.get_by_id(query.memory_id)


class ListMemoriesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListMemories) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_memories(
            scope=query.scope,
            project_id=query.project_id,
            session_id=query.session_id,
            limit=query.limit,
            offset=query.offset,
        )


class ListMemoriesByScopeHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListMemoriesByScope) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_memories(
            scope=query.scope,
            limit=query.limit,
        )


class ListMemoriesByProjectHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListMemoriesByProject) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_memories(
            project_id=query.project_id,
            limit=query.limit,
        )


class ListMemoriesBySessionHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListMemoriesBySession) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_memories(
            session_id=query.session_id,
            limit=query.limit,
        )


class SearchMemoriesByTagHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: SearchMemoriesByTag) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.search_by_tag(
            tag_key=query.tag_key,
            tag_value=query.tag_value,
            scope=query.scope,
            limit=query.limit,
        )


class ListMemoriesByStatusHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListMemoriesByStatus) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_by_status(
            validation_status=query.validation_status,
            scope=query.scope,
            limit=query.limit,
        )


class ListValidatedKnowledgeHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListValidatedKnowledge) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_validated_knowledge(
            scope=query.scope,
            min_confidence=query.min_confidence,
            project_id=query.project_id,
            limit=query.limit,
        )


class ListPoliciesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListPolicies) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_policies(
            validated_only=query.validated_only,
            project_id=query.project_id,
            limit=query.limit,
        )


class ListProceduralMemoriesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListProceduralMemories) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_procedural(
            project_id=query.project_id,
            limit=query.limit,
        )


class ListEpisodicMemoriesHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListEpisodicMemories) -> list[MemoryRecordView]:
        return await container_for(self._services).memory.list_episodic(
            session_id=query.session_id,
            limit=query.limit,
        )


class GetMemoryStatsHandler:
    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetMemoryStats) -> MemoryStatsView:
        return await container_for(self._services).memory.get_stats()


# --------------------------------------------------------------------------- #
# Job Handler
# --------------------------------------------------------------------------- #


class MemoryEvictExpiredJobHandler:
    job_type = "memory.evict_expired"

    def __init__(self, services: MemoryServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        scope = payload.get("scope")
        scope_str = str(scope) if isinstance(scope, str) else None
        cmd = EvictExpiredMemories(scope=scope_str)
        count = await container_for(self._services).memory.evict_expired(cmd)
        return {"evicted_count": count, "scope": scope_str, "status": "SUCCEEDED"}


__all__ = [
    "DeleteMemoryHandler",
    "EvictExpiredMemoriesHandler",
    "ForgetMemoryByPatternHandler",
    "ForgetMemoryHandler",
    "GetMemoryByIdHandler",
    "GetMemoryHandler",
    "GetMemoryStatsHandler",
    "ListEpisodicMemoriesHandler",
    "ListMemoriesByProjectHandler",
    "ListMemoriesByScopeHandler",
    "ListMemoriesBySessionHandler",
    "ListMemoriesByStatusHandler",
    "ListMemoriesHandler",
    "ListPoliciesHandler",
    "ListProceduralMemoriesHandler",
    "ListValidatedKnowledgeHandler",
    "MemoryEvictExpiredJobHandler",
    "SaveManyMemoriesHandler",
    "SaveMemoryHandler",
    "SearchMemoriesByTagHandler",
    "SetMemoryTtlHandler",
]
