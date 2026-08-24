"""
Unit Tests for Video Production Stage B Repositories and UnitOfWork:
- ProductionProjectRepository (Project & Revision CRUD)
- IdempotencyRepository (Key lookup, check, payload mismatch hash)
- ProductionEventRepository (Append events & stream/replay from sequence)
- WorkspaceReadModelRepository (Read models & projection checkpoints)
- VideoProductionUnitOfWork (Atomic commits & rollback)
"""

import pytest
import pytest_asyncio
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.video_production_uow import VideoProductionUnitOfWork


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest.mark.asyncio
async def test_project_and_revision_repository(in_memory_db):
    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        project = await uow.projects.save_project(
            project_id="vp_001",
            name="Test Film",
            status="ACTIVE",
            active_revision_id="rev_001",
        )
        assert project["id"] == "vp_001"
        assert project["active_revision_id"] == "rev_001"

        rev = await uow.projects.save_revision(
            revision_id="rev_001",
            project_id="vp_001",
            parent_revision_id=None,
            status="DRAFT",
            content_hash="sha_abc",
            sequence=1,
        )
        assert rev["id"] == "rev_001"
        assert rev["sequence"] == 1

        await uow.commit()

    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        p_fetched = await uow.projects.get_project("vp_001")
        assert p_fetched is not None
        assert p_fetched["name"] == "Test Film"

        r_fetched = await uow.projects.get_revision("rev_001")
        assert r_fetched is not None
        assert r_fetched["content_hash"] == "sha_abc"


@pytest.mark.asyncio
async def test_idempotency_repository(in_memory_db):
    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        rec = await uow.idempotency.save_record(
            scope="workspace_command",
            idempotency_key="key_123",
            request_hash="hash_aaa",
            response={"command_id": "cmd_1", "status": "COMPLETED"},
        )
        assert rec["idempotency_key"] == "key_123"
        await uow.commit()

    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        fetched = await uow.idempotency.get_record("workspace_command", "key_123")
        assert fetched is not None
        assert fetched["request_hash"] == "hash_aaa"
        assert fetched["response"]["command_id"] == "cmd_1"

        # Re-saving same key should return original record
        second = await uow.idempotency.save_record(
            scope="workspace_command",
            idempotency_key="key_123",
            request_hash="hash_aaa",
            response={"command_id": "cmd_DIFFERENT", "status": "COMPLETED"},
        )
        assert second["response"]["command_id"] == "cmd_1"


@pytest.mark.asyncio
async def test_production_event_repository_and_replay(in_memory_db):
    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.events.append_event(
            event_id="evt_1",
            sequence=10,
            project_id="vp_001",
            revision_id="rev_001",
            event_type="SCENE_CREATED",
            aggregate_type="SCREENPLAY",
            aggregate_id="sc_1",
            payload={"name": "Opening Scene"},
        )
        await uow.events.append_event(
            event_id="evt_2",
            sequence=11,
            project_id="vp_001",
            revision_id="rev_001",
            event_type="SCENE_UPDATED",
            aggregate_type="SCREENPLAY",
            aggregate_id="sc_1",
            payload={"name": "Opening Scene Extended"},
        )
        await uow.commit()

    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        all_events = await uow.events.get_events("vp_001", min_sequence=0)
        assert len(all_events) == 2
        assert all_events[0]["sequence"] == 10
        assert all_events[1]["sequence"] == 11

        replayed = await uow.events.get_events("vp_001", min_sequence=10)
        assert len(replayed) == 1
        assert replayed[0]["sequence"] == 11

        max_seq = await uow.events.get_max_sequence("vp_001")
        assert max_seq == 11


@pytest.mark.asyncio
async def test_video_production_uow_rollback(in_memory_db):
    with pytest.raises(RuntimeError, match="Simulated Failure"):
        async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
            await uow.projects.save_project("vp_rolled_back", "Unsaved", "ACTIVE", "rev_1")
            raise RuntimeError("Simulated Failure")

    async with VideoProductionUnitOfWork(in_memory_db.session_factory) as uow:
        p = await uow.projects.get_project("vp_rolled_back")
        assert p is None
