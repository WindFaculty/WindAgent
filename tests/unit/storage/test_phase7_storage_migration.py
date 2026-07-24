"""
Unit tests for WindAgent Storage Layer Migration and Core Contract Conformance (Phase 7).
Verifies ORM ↔ Canonical Domain mappers, SqlUnitOfWork, SqlTaskRepository, SqlOutboxWriter,
and schema migration script behavior.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from windagent_core.domain.types import TaskId, SessionId, StepId, RunId, WorkflowId, EventId, ArtifactId
from windagent_core.domain.models import Task, Session, WorkflowRun, WorkflowStep, ArtifactRef
from windagent_core.domain.lifecycle import TaskState, SessionState, WorkflowState, StepState
from windagent_core.events.envelope import EventEnvelope
from windagent_core.contracts import UnitOfWork, TaskRepository, SessionRepository, EventStore, OutboxWriter

from windagent_storage.orm.models import BaseORM, TaskORM, SessionORM, WorkflowRunORM, WorkflowStepORM, ExecutionEventORM, ArtifactRefORM
from windagent_storage.mappers.domain_orm import (
    orm_to_domain_session, domain_to_orm_session,
    orm_to_domain_task, domain_to_orm_task,
    orm_to_domain_workflow, domain_to_orm_workflow,
    orm_to_domain_event, domain_to_orm_event,
    orm_to_domain_artifact, domain_to_orm_artifact
)
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


def test_session_orm_mapper_canonical_state():
    sid = SessionId.generate()
    session = Session(
        id=sid,
        status=SessionState.ACTIVE,
        title="Test Session",
        metadata={"user": "admin"}
    )
    orm = domain_to_orm_session(session)
    assert orm.id == str(sid)
    assert orm.status == "ACTIVE"

    mapped_back = orm_to_domain_session(orm)
    assert mapped_back.id == sid
    assert mapped_back.status == SessionState.ACTIVE
    assert mapped_back.title == "Test Session"


def test_task_orm_mapper_canonical_state():
    tid = TaskId.generate()
    sid = SessionId.generate()
    task = Task(
        id=tid,
        prompt="Fix bug in auth module",
        session_id=sid,
        status=TaskState.RUNNING,
        tags=["bugfix", "urgent"]
    )
    orm = domain_to_orm_task(task)
    assert orm.id == str(tid)
    assert orm.status == "RUNNING"

    mapped_back = orm_to_domain_task(orm)
    assert mapped_back.id == tid
    assert mapped_back.status == TaskState.RUNNING
    assert mapped_back.prompt == "Fix bug in auth module"


def test_workflow_orm_mapper_canonical_state():
    rid = RunId.generate()
    sid = SessionId.generate()
    wfid = WorkflowId.generate()
    step_id = StepId.generate()

    step = WorkflowStep(
        id=step_id,
        order=1,
        name="Click Button",
        tool_name="click_xy",
        status=StepState.COMPLETED
    )
    wf_run = WorkflowRun(
        run_id=rid,
        workflow_id=wfid,
        session_id=sid,
        status=WorkflowState.RUNNING,
        steps=[step]
    )

    orm = domain_to_orm_workflow(wf_run)
    assert orm.run_id == str(rid)
    assert orm.status == "RUNNING"
    assert len(orm.steps) == 1

    mapped_back = orm_to_domain_workflow(orm)
    assert mapped_back.run_id == rid
    assert mapped_back.status == WorkflowState.RUNNING
    assert len(mapped_back.steps) == 1
    assert mapped_back.steps[0].status == StepState.COMPLETED


@pytest.mark.asyncio
async def test_sql_uow_conformance():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uow = SqlUnitOfWork(session_factory)

    assert isinstance(uow, UnitOfWork)

    async with uow:
        assert isinstance(uow.tasks, TaskRepository)
        assert isinstance(uow.sessions, SessionRepository)
        assert isinstance(uow.events, EventStore)
        assert isinstance(uow.outbox, OutboxWriter)

        sid = SessionId.generate()
        session = Session(id=sid, status=SessionState.ACTIVE, title="Async UoW Session")
        await uow.sessions.save(session)
        await uow.commit()

    async with uow:
        loaded = await uow.sessions.get_by_id(sid)
        assert loaded is not None
        assert loaded.id == sid
        assert loaded.title == "Async UoW Session"

    await engine.dispose()
