"""Immutable Memory queries (Phase 14)."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import MemoryRecordView, MemoryStatsView


@dataclass(frozen=True, slots=True)
class GetMemory(Query[MemoryRecordView | None]):
    scope: str
    key: str
    project_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetMemoryById(Query[MemoryRecordView | None]):
    memory_id: str


@dataclass(frozen=True, slots=True)
class ListMemories(Query[list[MemoryRecordView]]):
    scope: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListMemoriesByScope(Query[list[MemoryRecordView]]):
    scope: str
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListMemoriesByProject(Query[list[MemoryRecordView]]):
    project_id: str
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListMemoriesBySession(Query[list[MemoryRecordView]]):
    session_id: str
    limit: int = 100


@dataclass(frozen=True, slots=True)
class SearchMemoriesByTag(Query[list[MemoryRecordView]]):
    tag_key: str
    tag_value: str
    scope: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListMemoriesByStatus(Query[list[MemoryRecordView]]):
    validation_status: str
    scope: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListValidatedKnowledge(Query[list[MemoryRecordView]]):
    scope: str | None = None
    min_confidence: float = 0.0
    project_id: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListPolicies(Query[list[MemoryRecordView]]):
    validated_only: bool = True
    project_id: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListProceduralMemories(Query[list[MemoryRecordView]]):
    project_id: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListEpisodicMemories(Query[list[MemoryRecordView]]):
    session_id: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class GetMemoryStats(Query[MemoryStatsView]):
    pass
