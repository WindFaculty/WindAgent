"""SQL Work Submission Adapter for WindAgent Storage Layer (Phase 3).

Submits task requests into task_runs table and inserts outbox event TaskSubmitted
in a single atomic SQL transaction.
"""

from __future__ import annotations
import json
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.contracts.workers.submission import WorkSubmissionPort
from windagent_core.contracts.workers.models import WorkSubmission
from windagent_storage.orm.v2_orchestration_models import TaskRunORM
from windagent_storage.orm.models import OutboxRecordORM

logger = logging.getLogger("windagent.storage.queue.submission")


class SqlWorkSubmissionAdapter(WorkSubmissionPort):
    """Adapter that writes task run and outbox event TaskSubmitted in a single transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def submit(self, request: WorkSubmission) -> str:
        """Atomically saves task run record and inserts TaskSubmitted outbox event."""
        task_id = request.task_id or f"tsk_{uuid.uuid4().hex[:12]}"
        session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        facts_json = json.dumps({
            "prompt": request.prompt,
            "tool_name": request.tool_name or "read_file",
            "parameters": request.parameters or {},
            "workflow_name": request.workflow_name or "bugfix",
            "session_id": session_id,
        })

        async with self._session_factory() as session:
            async with session.begin():
                # 1. Insert task run record
                task_orm = TaskRunORM(
                    id=task_id,
                    session_id=session_id,
                    state="pending",
                    version=1,
                    priority=request.priority if hasattr(request, "priority") else 2,
                    current_step=0,
                    total_steps=1,
                    facts_json=facts_json,
                    created_at=now_naive,
                    updated_at=now_naive,
                )
                session.add(task_orm)

                # 2. Insert outbox record TaskSubmitted
                outbox_id = f"out_{uuid.uuid4().hex[:12]}"
                event_id = str(uuid.uuid4())
                payload_json = json.dumps({
                    "task_id": task_id,
                    "session_id": session_id,
                    "prompt": request.prompt,
                    "tool_name": request.tool_name or "read_file",
                })

                outbox_orm = OutboxRecordORM(
                    id=outbox_id,
                    event_id=event_id,
                    aggregate_id=task_id,
                    aggregate_type="task",
                    event_type="TaskSubmitted",
                    payload_json=payload_json,
                    schema_version="2.0",
                    sequence_number=1,
                    deduplication_key=request.idempotency_key,
                    created_at=now_naive,
                    available_at=now_naive,
                    status="pending",
                    attempt_count=0,
                )
                session.add(outbox_orm)

                logger.info(f"Task [{task_id}] submitted atomically with TaskSubmitted outbox record [{outbox_id}]")

        return task_id
