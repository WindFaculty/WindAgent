"""Unit tests for SqlWorkRepository (WorkRepository core contract).

Exercises the submit/get/claim/complete/list_pending lifecycle mapped onto the
TaskRunORM table via facts_json — the corrected mapping that matches
SqlWorkSubmissionAdapter's persistence pattern.

Note: DatabaseManager configures autoflush=False, so tests commit after each
write and read back through a fresh session (mirroring the SqlUnitOfWork flow,
where the caller commits at transaction end).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from windagent_core.contracts.workers.models import WorkSubmission
from windagent_core.domain.types import TaskId
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v2_orchestration_models import TaskRunORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.repositories.sql_repositories import SqlWorkRepository

# TaskId is a UUID-validated identity type (see core/windagent_core/domain/types.py),
# so test fixtures must use well-formed UUID strings.
TASK_UUID = "123e4567-e89b-12d3-a456-426614174000"
TASK_UUID_A = "123e4567-e89b-12d3-a456-426614174001"
TASK_UUID_B = "123e4567-e89b-12d3-a456-426614174002"
TASK_UUID_FAIL = "123e4567-e89b-12d3-a456-4266141740ff"


@pytest.fixture
async def db_manager():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_submit_persists_pending_row_and_roundtrips(db_manager):
    """submit() writes a pending task_runs row; get() reconstructs the contract."""
    async with db_manager.session_factory() as session:
        repo = SqlWorkRepository(session)
        req = WorkSubmission(
            prompt="Fix auth bypass",
            task_id=TASK_UUID,
            session_id="sess_abc",
            workflow_name="security",
            idempotency_key="idem-1",
            tool_name="code_search",
            parameters={"query": "auth_bypass"},
        )
        await repo.submit(req)
        await session.commit()

    async with db_manager.session_factory() as session:
        res = await session.execute(select(TaskRunORM).where(TaskRunORM.id == TASK_UUID))
        orm = res.scalar_one_or_none()
        assert orm is not None
        assert orm.state == "pending"

        got = await SqlWorkRepository(session).get(TaskId(TASK_UUID))
        assert got is not None
        assert got.prompt == "Fix auth bypass"
        assert got.task_id == TASK_UUID
        assert got.session_id == "sess_abc"
        assert got.workflow_name == "security"
        assert got.idempotency_key == "idem-1"
        assert got.tool_name == "code_search"
        assert got.parameters == {"query": "auth_bypass"}


@pytest.mark.asyncio
async def test_submit_generates_ids_when_absent(db_manager):
    """submit() fills task_id/session_id when the request omits them."""
    import uuid

    async with db_manager.session_factory() as session:
        await SqlWorkRepository(session).submit(WorkSubmission(prompt="Generate ids test"))
        await session.commit()

    async with db_manager.session_factory() as session:
        pend = await SqlWorkRepository(session).list_pending()
        assert len(pend) == 1
        assert pend[0].prompt == "Generate ids test"
        # Generated ids are well-formed UUIDs so they round-trip through the
        # UUID-validated TaskId/SessionId identity types.
        uuid.UUID(pend[0].task_id)
        uuid.UUID(pend[0].session_id)
        assert TaskId(pend[0].task_id).value is not None


@pytest.mark.asyncio
async def test_claim_complete_lifecycle(db_manager):
    """claim() moves pending->running; complete() moves to completed with result."""
    async with db_manager.session_factory() as session:
        repo = SqlWorkRepository(session)
        await repo.submit(
            WorkSubmission(prompt="Claimable task", task_id=TASK_UUID, session_id="sess_1")
        )
        await session.commit()

    async with db_manager.session_factory() as session:
        repo = SqlWorkRepository(session)
        claimed = await repo.claim(TaskId(TASK_UUID), worker_id="wkr_9", lease_seconds=60)
        assert claimed is True
        await session.commit()

    async with db_manager.session_factory() as session:
        res = await session.execute(select(TaskRunORM).where(TaskRunORM.id == TASK_UUID))
        orm = res.scalar_one_or_none()
        assert orm is not None
        assert orm.state == "running"
        assert orm.facts_json is not None
        assert '"assigned_worker_id": "wkr_9"' in orm.facts_json

        # Second claim while running must fail
        assert await SqlWorkRepository(session).claim(TaskId(TASK_UUID), worker_id="wkr_10") is False

        await SqlWorkRepository(session).complete(TaskId(TASK_UUID), result={"output": "done"})
        await session.commit()

    async with db_manager.session_factory() as session:
        res = await session.execute(select(TaskRunORM).where(TaskRunORM.id == TASK_UUID))
        orm = res.scalar_one_or_none()
        assert orm is not None
        assert orm.state == "completed"
        assert '"result": {"output": "done"}' in orm.facts_json


@pytest.mark.asyncio
async def test_complete_with_error_marks_failed_and_last_error(db_manager):
    """complete(error=...) sets failed state and persists last_error column."""
    async with db_manager.session_factory() as session:
        await SqlWorkRepository(session).submit(WorkSubmission(prompt="Failing task", task_id=TASK_UUID))
        await session.commit()

    async with db_manager.session_factory() as session:
        await SqlWorkRepository(session).complete(TaskId(TASK_UUID), error="boom")
        await session.commit()

    async with db_manager.session_factory() as session:
        res = await session.execute(select(TaskRunORM).where(TaskRunORM.id == TASK_UUID))
        orm = res.scalar_one_or_none()
        assert orm is not None
        assert orm.state == "failed"
        assert orm.last_error == "boom"


@pytest.mark.asyncio
async def test_list_pending_only_returns_pending(db_manager):
    """list_pending() excludes running/completed items."""
    async with db_manager.session_factory() as session:
        repo = SqlWorkRepository(session)
        await repo.submit(WorkSubmission(prompt="A", task_id=TASK_UUID_A))
        await repo.submit(WorkSubmission(prompt="B", task_id=TASK_UUID_B))
        await session.commit()

    async with db_manager.session_factory() as session:
        await SqlWorkRepository(session).claim(TaskId(TASK_UUID_A), worker_id="wkr_1")
        await session.commit()

    async with db_manager.session_factory() as session:
        pend = await SqlWorkRepository(session).list_pending()
        assert [p.task_id for p in pend] == [TASK_UUID_B]


@pytest.mark.asyncio
async def test_get_missing_returns_none(db_manager):
    """get() returns None for an unknown task id."""
    async with db_manager.session_factory() as session:
        assert await SqlWorkRepository(session).get(TaskId(TASK_UUID_FAIL)) is None
