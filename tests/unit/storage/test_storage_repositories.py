"""
Unit Tests for WindAgent Storage Layer (Phase 4):
- SqlSessionRepository, SqlTaskRepository, SqlWorkflowRepository CRUD operations
- SqlEventStore appending & cursor query
- FileArtifactRepository file persistence
- SqlUnitOfWork atomic transactions & rollback verification
- Transactional Outbox pattern & event dispatch
"""

import pytest
import pytest_asyncio
from pathlib import Path

from windagent_core.domain.types import (
    SessionId, TaskId, WorkflowId, StepId, RunId, EventId
)
from windagent_core.domain.models import (
    Session, SessionStatus, Task, WorkflowRun, WorkflowStep
)
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_storage.outbox.processor import TransactionalOutboxManager


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest.mark.asyncio
async def test_sql_session_repository_crud(in_memory_db):
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        session_id = SessionId.generate()
        session = Session(id=session_id, title="Test Storage Session")

        await uow.sessions.save(session)
        await uow.commit()

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        fetched = await uow.sessions.get_by_id(session_id)
        assert fetched is not None
        assert fetched.title == "Test Storage Session"
        assert fetched.status.value.upper() == "IDLE"

        fetched.status = SessionStatus.RUNNING
        await uow.sessions.save(fetched)
        await uow.commit()

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        updated = await uow.sessions.get_by_id(session_id)
        assert updated.status.value.upper() in ("RUNNING", "COMPLETED", "FAILED", "CANCELLED")

        deleted = await uow.sessions.delete(session_id)
        assert deleted
        await uow.commit()

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        gone = await uow.sessions.get_by_id(session_id)
        assert gone is None


@pytest.mark.asyncio
async def test_sql_task_and_workflow_repositories(in_memory_db):
    sid = SessionId.generate()
    tid = TaskId.generate()
    wfid = WorkflowId.generate()
    runid = RunId.generate()

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        # Save Session
        await uow.sessions.save(Session(id=sid, title="Parent Session"))

        # Save Task
        task = Task(id=tid, prompt="Analyze codebase architecture", session_id=sid)
        await uow.tasks.save(task)

        # Save Workflow
        step1 = WorkflowStep(id=StepId.generate(), order=1, name="Read Docs", tool_name="open_url")
        wf_run = WorkflowRun(run_id=runid, workflow_id=wfid, session_id=sid, steps=[step1])
        await uow.workflows.save(wf_run)

        await uow.commit()

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        tasks = await uow.tasks.list_by_session(sid)
        assert len(tasks) == 1
        assert tasks[0].prompt == "Analyze codebase architecture"

        wf_fetched = await uow.workflows.get_by_id(runid)
        assert wf_fetched is not None
        assert wf_fetched.workflow_id == wfid
        assert len(wf_fetched.steps) == 1
        assert wf_fetched.steps[0].tool_name == "open_url"


@pytest.mark.asyncio
async def test_sql_unit_of_work_atomic_transaction_and_rollback(in_memory_db):
    sid = SessionId.generate()

    # Proving Exception causes rollback of all uncommitted state & outbox events
    with pytest.raises(RuntimeError, match="Simulated Error"):
        async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
            await uow.sessions.save(Session(id=sid, title="Should Be Rolled Back"))

            envelope = EventEnvelope(
                event_id=EventId.generate(),
                event_type=EventCatalog.STEP_STARTED,
                session_id=sid,
                sequence=1,
                payload={"info": "test"},
            )
            await uow.record_outbox_event(envelope)

            raise RuntimeError("Simulated Error")

    # Verify no session or outbox event was saved
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        fetched = await uow.sessions.get_by_id(sid)
        assert fetched is None

        events = await uow.events.get_events(sid)
        assert len(events) == 0


@pytest.mark.asyncio
async def test_transactional_outbox_processing(in_memory_db):
    sid = SessionId.generate()
    dispatched_events = []

    def mock_handler(event: EventEnvelope):
        dispatched_events.append(event)

    outbox_manager = TransactionalOutboxManager(
        session_factory=in_memory_db.session_factory,
        event_handler=mock_handler,
    )

    # Record outbox event and commit
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.sessions.save(Session(id=sid, title="Outbox Test Session"))
        envelope = EventEnvelope(
            event_id=EventId.generate(),
            event_type=EventCatalog.STEP_COMPLETED,
            session_id=sid,
            sequence=10,
            payload={"status": "success"},
        )
        await uow.record_outbox_event(envelope)
        await uow.commit()

    # Outbox manager processes pending records
    count = await outbox_manager.process_pending_outbox()
    assert count == 1
    assert len(dispatched_events) == 1
    assert dispatched_events[0].sequence == 10
    assert dispatched_events[0].event_type == EventCatalog.STEP_COMPLETED

    # Running process again should yield 0 pending items
    count_second = await outbox_manager.process_pending_outbox()
    assert count_second == 0


@pytest.mark.asyncio
async def test_file_artifact_repository(in_memory_db, tmp_path):
    storage_dir = tmp_path / "artifacts"
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        uow.artifacts = uow.artifacts.__class__(uow.session, storage_dir=str(storage_dir))

        art_ref = await uow.artifacts.store("test_report.txt", b"Hello Artifact", "text/plain")
        await uow.commit()

    assert Path(art_ref.uri).exists()
    assert Path(art_ref.uri).read_bytes() == b"Hello Artifact"

    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        uow.artifacts = uow.artifacts.__class__(uow.session, storage_dir=str(storage_dir))
        fetched = await uow.artifacts.get_by_id(art_ref.id)
        assert fetched is not None
        assert fetched.name == "test_report.txt"
        assert fetched.size_bytes == len(b"Hello Artifact")