"""Unit tests for Memory application services and orchestration (Phase 14)."""

from __future__ import annotations

import pytest
from windagent.modules.memory.application.commands import (
    EvictExpiredMemories,
    ForgetMemoryByPattern,
    SaveManyMemories,
    SaveMemory,
    SetMemoryTtl,
)
from windagent.modules.memory.application.services import MemoryService
from windagent.modules.memory.domain.errors import (
    MemoryNotFoundError,
    MemoryStaleVersionError,
)
from windagent.modules.memory.infrastructure.memory import (
    InMemoryMemoryStore,
    memory_scope_factory,
)


@pytest.fixture
def memory_fixture() -> tuple[MemoryService, InMemoryMemoryStore]:
    store = InMemoryMemoryStore()
    factory = memory_scope_factory(store)
    service = MemoryService(scope_factory=factory)
    return service, store


@pytest.mark.asyncio
async def test_save_and_get_memory(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    cmd = SaveMemory(
        scope="working",
        key="current_task",
        value={"title": "Implement memory module", "progress": 50},
        provenance_source="agent_runtime",
        tags={"category": "dev"},
    )
    view = await service.save_memory(cmd)

    assert view.key == "current_task"
    assert view.scope == "working"
    assert view.value == {"title": "Implement memory module", "progress": 50}
    assert view.version == 1
    assert view.optimistic_version == 1
    assert len(store.events) == 1
    assert store.events[0].event_type == "memory.created"

    # Get by scope and key
    fetched = await service.get_memory(scope="working", key="current_task")
    assert fetched is not None
    assert fetched.id == view.id
    assert fetched.tags == {"category": "dev"}


@pytest.mark.asyncio
async def test_update_existing_memory(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    # Initial save
    v1 = await service.save_memory(
        SaveMemory(
            scope="project",
            key="db_host",
            value="localhost",
            provenance_source="config",
            project_id="proj_1",
        )
    )
    assert v1.version == 1

    # Update with new value
    v2 = await service.save_memory(
        SaveMemory(
            scope="project",
            key="db_host",
            value="postgres.internal",
            provenance_source="config",
            project_id="proj_1",
            expected_version=1,
        )
    )
    assert v2.id == v1.id
    assert v2.value == "postgres.internal"
    assert v2.version == 2
    assert v2.optimistic_version == 2

    # Stale version check
    with pytest.raises(MemoryStaleVersionError):
        await service.save_memory(
            SaveMemory(
                scope="project",
                key="db_host",
                value="broken",
                provenance_source="config",
                project_id="proj_1",
                expected_version=1,  # Outdated version!
            )
        )


@pytest.mark.asyncio
async def test_content_hash_deduplication(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    # Save record 1
    v1 = await service.save_memory(
        SaveMemory(
            scope="semantic",
            key="rule_duplicate",
            value="Exact identical text payload",
            provenance_source="analysis",
        )
    )

    # Save record 2 with same key and value -> deduplicated to same record
    v2 = await service.save_memory(
        SaveMemory(
            scope="semantic",
            key="rule_duplicate",
            value="Exact identical text payload",
            provenance_source="analysis",
        )
    )

    assert v1.id == v2.id
    assert v1.content_hash == v2.content_hash
    # Store has only 1 physical record
    assert len(store.records) == 1


@pytest.mark.asyncio
async def test_superseding_lineage(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    # 1. Save old rule
    v_old = await service.save_memory(
        SaveMemory(
            scope="policy",
            key="old_guideline",
            value="Do not use async",
            provenance_source="legacy",
            learning_metadata={
                "confidence": 0.8,
                "sample_size": 2,
                "validation_status": "validated",
                "evidence_refs": ["ref1"],
            },
        )
    )
    assert v_old.learning_metadata["validation_status"] == "validated"

    # 2. Save new rule that supersedes old rule
    v_new = await service.save_memory(
        SaveMemory(
            scope="policy",
            key="new_guideline",
            value="Use async everywhere",
            provenance_source="v2",
            learning_metadata={
                "confidence": 0.95,
                "sample_size": 5,
                "validation_status": "promoted",
                "evidence_refs": ["ref2"],
                "supersedes_id": v_old.id,
            },
        )
    )

    # 3. Old rule is now marked SUPERSEDED
    old_fetched = await service.get_by_id(v_old.id)
    assert old_fetched is not None
    assert old_fetched.learning_metadata["validation_status"] == "superseded"

    # Verify outbox has memory.superseded event
    superseded_events = [e for e in store.events if e.event_type == "memory.superseded"]
    assert len(superseded_events) == 1
    assert superseded_events[0].payload["superseded_by_id"] == v_new.id


@pytest.mark.asyncio
async def test_delete_and_forget_by_pattern(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    await service.save_memory(
        SaveMemory(scope="working", key="cache:user:1", value="Alice", provenance_source="api")
    )
    await service.save_memory(
        SaveMemory(scope="working", key="cache:user:2", value="Bob", provenance_source="api")
    )
    await service.save_memory(
        SaveMemory(scope="working", key="other:item", value="Data", provenance_source="api")
    )

    # Forget pattern "cache:user:"
    count = await service.forget_by_pattern(
        ForgetMemoryByPattern(scope="working", key_prefix="cache:user:")
    )
    assert count == 2

    # Verify remaining
    assert await service.get_memory("working", "cache:user:1") is None
    assert await service.get_memory("working", "cache:user:2") is None
    assert await service.get_memory("working", "other:item") is not None


@pytest.mark.asyncio
async def test_ttl_and_eviction(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    # Save with 1 second TTL
    await service.save_memory(
        SaveMemory(
            scope="working",
            key="short_lived",
            value="flash",
            provenance_source="test",
            ttl_seconds=1,
        )
    )

    # Update TTL
    await service.set_ttl(SetMemoryTtl(scope="working", key="short_lived", ttl_seconds=0))

    # Setting non-existent TTL raises
    with pytest.raises(MemoryNotFoundError):
        await service.set_ttl(SetMemoryTtl(scope="working", key="ghost", ttl_seconds=10))

    # Trigger eviction
    evicted_count = await service.evict_expired(EvictExpiredMemories(scope="working"))
    assert evicted_count == 1
    assert await service.get_memory("working", "short_lived") is None


@pytest.mark.asyncio
async def test_batch_save_and_queries(
    memory_fixture: tuple[MemoryService, InMemoryMemoryStore],
) -> None:
    service, store = memory_fixture

    # Batch save
    saved = await service.save_many(
        SaveManyMemories(
            records=[
                {
                    "key": "p1",
                    "value": "Recipe 1",
                    "scope": "procedural",
                    "provenance_source": "system",
                    "project_id": "proj_a",
                    "tags": {"env": "prod"},
                },
                {
                    "key": "p2",
                    "value": "Recipe 2",
                    "scope": "procedural",
                    "provenance_source": "system",
                    "project_id": "proj_a",
                    "tags": {"env": "prod"},
                },
                {
                    "key": "ep1",
                    "value": "Episode trace",
                    "scope": "episodic",
                    "provenance_source": "system",
                    "session_id": "sess_1",
                },
            ]
        )
    )
    assert len(saved) == 3

    # Queries
    procedural = await service.list_procedural(project_id="proj_a")
    assert len(procedural) == 2

    episodic = await service.list_episodic(session_id="sess_1")
    assert len(episodic) == 1

    by_tag = await service.search_by_tag(tag_key="env", tag_value="prod")
    assert len(by_tag) == 2

    stats = await service.get_stats()
    assert stats.total_records == 3
    assert stats.by_scope["procedural"] == 2
    assert stats.by_scope["episodic"] == 1
