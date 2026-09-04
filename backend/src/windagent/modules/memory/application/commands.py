"""Immutable Memory commands (Phase 14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import MemoryRecordView


@dataclass(frozen=True, slots=True)
class SaveMemory(Command[MemoryRecordView]):
    key: str
    value: Any
    scope: str = "working"
    provenance_source: str = ""
    project_id: str | None = None
    session_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    ttl_seconds: int | None = None
    learning_metadata: dict[str, Any] = field(default_factory=dict)
    expected_version: int | None = None
    memory_id: str | None = None


@dataclass(frozen=True, slots=True)
class SaveManyMemories(Command[list[MemoryRecordView]]):
    records: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DeleteMemory(Command[bool]):
    scope: str
    key: str
    project_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ForgetMemory(Command[bool]):
    scope: str
    key: str
    project_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ForgetMemoryByPattern(Command[int]):
    scope: str
    key_prefix: str
    project_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class SetMemoryTtl(Command[bool]):
    scope: str
    key: str
    ttl_seconds: int
    project_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvictExpiredMemories(Command[int]):
    scope: str | None = None
