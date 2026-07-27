"""
SQL Repository Implementations for WindAgent Storage.

Provides concrete SQLAlchemy implementations of core storage contracts:
- SqlEventStore: Event persistence with sequence management
- SqlSessionRepository: Session state persistence
- SqlWorkflowRepository: Workflow execution persistence
- SqlWorkRepository: Task work submission and lease management
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.contracts import (
    EventStore,
    OutboxWriter,
    SessionRepository,
    WorkRepository,
    WorkSubmission,
    WorkflowRepository,
    WorkflowRun,
    WorkflowState,
)
from windagent_core.events.envelope import EventEnvelope
from windagent_core.domain.types import (
    AggregateId,
    ArtifactId,
    EventId,
    SessionId,
    StepId,
    StepRunId,
    TaskId,
    TaskRunId,
    WorkflowId,
    WorkflowRunId,
)
from windagent_core.domain.models import (
    ArtifactRef,
    Session,
    SessionStatus,
    StepStatus,
    Task,
    WorkflowRun as DomainWorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from windagent_storage.orm.models import (
    ExecutionEventORM,
    OutboxRecordORM,
    SessionORM,
    TaskORM,
    WorkflowRunORM,
    WorkflowStepORM,
)
from windagent_storage.orm.v2_orchestration_models import (
    WorkflowStepRunORM,
    TaskRunORM,
    WorkflowRunV2ORM,
)
from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_storage.mappers.domain_orm import domain_to_orm_event

logger = logging.getLogger("windagent.storage.repositories.sql")


class FileArtifactRepository:
    """File-based artifact storage implementation."""

    def __init__(self, session: AsyncSession, storage_dir: str = "./artifacts"):
        self._session = session
        self._storage_dir = storage_dir

    async def store(self, name: str, data: bytes, mime_type: str) -> ArtifactRef:
        import hashlib

        artifact_id = ArtifactId.generate()
        content_hash = hashlib.sha256(data).hexdigest()
        # Store file to disk (simplified)
        import os

        storage_path = os.path.join(self._storage_dir, str(artifact_id))
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        with open(storage_path, "wb") as f:
            f.write(data)
        # Store name in a sidecar metadata file
        meta_path = storage_path + ".meta"
        with open(meta_path, "w") as f:
            f.write(name)
        return ArtifactRef(
            id=artifact_id,
            name=name,
            mime_type=mime_type,
            uri=storage_path,
            size_bytes=len(data),
            metadata={"content_hash": content_hash},
        )

    async def get_by_id(self, artifact_id: ArtifactId) -> Optional[ArtifactRef]:
        import os

        storage_path = os.path.join(self._storage_dir, str(artifact_id))
        if not os.path.exists(storage_path):
            return None
        stat = os.stat(storage_path)
        # Read original name from metadata file
        meta_path = storage_path + ".meta"
        name = str(artifact_id)
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                name = f.read().strip()
        return ArtifactRef(
            id=artifact_id,
            name=name,
            mime_type="application/octet-stream",
            uri=storage_path,
            size_bytes=stat.st_size,
            metadata={"content_hash": "stored"},
        )


class SqlProviderConfigurationRepository:
    """Provider configuration repository implementation."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, provider_id: str) -> Optional[dict]:
        return None

    async def list_all(self) -> List[dict]:
        return []


class SqlEventStore:
    """SQL Implementation for EventStore core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, event: EventEnvelope) -> None:
        # Assign next sequence number if not already set
        if event.sequence == 0:
            from sqlalchemy import select, func

            agg_id = (
                str(event.session_id) if event.session_id else str(event.aggregate_id)
            )
            stmt = select(func.max(ExecutionEventORM.event_seq)).where(
                ExecutionEventORM.session_id == agg_id
            )
            res = await self._session.execute(stmt)
            max_seq = res.scalar() or 0
            object.__setattr__(event, "sequence", max_seq + 1)

        orm = domain_to_orm_event(event)
        self._session.add(orm)

    async def append_event(self, event: EventEnvelope) -> None:
        await self.append(event)

    async def get_events(
        self, stream_id: Any, after_sequence: int = 0, limit: int = 100
    ) -> List[EventEnvelope]:
        stmt = (
            select(ExecutionEventORM)
            .where(ExecutionEventORM.session_id == str(stream_id))
            .where(ExecutionEventORM.event_seq > after_sequence)
            .order_by(ExecutionEventORM.event_seq.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        events = []
        for orm in orms:
            data = json.loads(orm.data_json) if orm.data_json else {}
            aggregate_id_str = data.get("aggregate_id", str(stream_id))
            events.append(
                EventEnvelope(
                    event_id=EventId(orm.id),
                    event_type=orm.event_type,
                    aggregate_id=aggregate_id_str,
                    aggregate_type=data.get("aggregate_type", "session"),
                    sequence=orm.event_seq,
                    occurred_at=orm.created_at,
                    payload=data.get("payload", {}),
                    metadata=data.get("metadata", {}),
                )
            )
        return events


class SqlSessionRepository:
    """SQL Implementation for SessionRepository core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, session_obj: Session) -> None:
        orm = SessionORM(
            id=str(session_obj.id),
            title=session_obj.title,
            created_at=session_obj.created_at,
            updated_at=session_obj.updated_at,
            status=session_obj.status.value if session_obj.status else "idle",
            metadata_json=json.dumps(session_obj.metadata)
            if session_obj.metadata
            else "{}",
        )
        await self._session.merge(orm)

    async def get(self, session_id: SessionId) -> Optional[Session]:
        stmt = select(SessionORM).where(SessionORM.id == str(session_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return Session(
            id=SessionId(orm.id),
            title=orm.title,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            status=SessionStatus(orm.status),
            metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
        )

    async def get_by_id(self, session_id: SessionId) -> Optional[Session]:
        return await self.get(session_id)

    async def list_all(self) -> List[Session]:
        stmt = select(SessionORM).order_by(SessionORM.created_at.desc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        sessions = []
        for orm in orms:
            sessions.append(
                Session(
                    id=SessionId(orm.id),
                    title=orm.title,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    status=SessionStatus(orm.status),
                    metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
                )
            )
        return sessions

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        stmt = (
            select(SessionORM)
            .order_by(SessionORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        sessions = []
        for orm in orms:
            sessions.append(
                Session(
                    id=SessionId(orm.id),
                    title=orm.title,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    status=SessionStatus(orm.status),
                    metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
                )
            )
        return sessions

    async def delete(self, session_id: SessionId) -> bool:
        stmt = select(SessionORM).where(SessionORM.id == str(session_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return False
        await self._session.delete(orm)
        return True


class SqlWorkflowRepository:
    """SQL Implementation for WorkflowRepository core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, workflow: WorkflowRun) -> None:
        orm = WorkflowRunV2ORM(
            run_id=str(workflow.run_id),
            workflow_id=str(workflow.workflow_id),
            session_id=str(workflow.session_id),
            state=workflow.status.value if workflow.status else "pending",
            definition_json=json.dumps(
                {
                    "steps": [
                        {
                            "id": str(s.id),
                            "order": s.order,
                            "name": s.name,
                            "tool_name": s.tool_name,
                            "params": s.params,
                            "status": s.status.value
                            if hasattr(s.status, "value")
                            else str(s.status),
                            "result": s.result,
                            "error": s.error,
                        }
                        for s in workflow.steps
                    ]
                }
            )
            if workflow.steps
            else "{}",
        )
        await self._session.merge(orm)

    async def get(self, workflow_id: WorkflowId) -> Optional[WorkflowRun]:
        stmt = select(WorkflowRunV2ORM).where(
            WorkflowRunV2ORM.run_id == str(workflow_id)
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        # Parse steps from definition_json
        steps = []
        if orm.definition_json:
            try:
                def_json = json.loads(orm.definition_json)
                for s in def_json.get("steps", []):
                    steps.append(
                        WorkflowStep(
                            id=StepId(s["id"]),
                            order=s["order"],
                            name=s["name"],
                            tool_name=s["tool_name"],
                            params=s.get("params", {}),
                            status=StepStatus(s["status"])
                            if s.get("status")
                            else StepStatus.PENDING,
                            result=s.get("result"),
                            error=s.get("error"),
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                pass
        return WorkflowRun(
            run_id=WorkflowId(orm.run_id),
            workflow_id=WorkflowId(orm.workflow_id),
            session_id=SessionId(orm.session_id),
            created_at=orm.created_at,
            status=WorkflowStatus(orm.state) if orm.state else WorkflowStatus.PENDING,
            steps=steps,
        )

    async def get_by_id(self, workflow_id: WorkflowId) -> Optional[WorkflowRun]:
        return await self.get(workflow_id)

    async def list_all(self) -> List[WorkflowRun]:
        stmt = select(WorkflowRunV2ORM).order_by(WorkflowRunV2ORM.created_at.desc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        workflows = []
        for orm in orms:
            workflows.append(
                WorkflowRun(
                    id=WorkflowId(orm.id),
                    workflow_type=orm.workflow_type,
                    state=orm.state,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    payload=json.loads(orm.payload_json) if orm.payload_json else {},
                    metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
                )
            )
        return workflows


class SqlWorkRepository:
    """SQL Implementation for WorkRepository core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def submit(self, work: WorkSubmission) -> None:
        orm = TaskRunV2ORM(
            id=str(work.id),
            task_type=work.task_type,
            state=work.state.value if work.state else "pending",
            created_at=work.created_at,
            updated_at=work.updated_at,
            payload_json=json.dumps(work.payload) if work.payload else "{}",
            result_json=json.dumps(work.result) if work.result else None,
            error=work.error,
            workflow_run_id=str(work.workflow_run_id) if work.workflow_run_id else None,
            step_run_id=work.step_run_id,
            assigned_worker_id=work.assigned_worker_id,
        )
        await self._session.merge(orm)

    async def get(self, task_id: TaskId) -> Optional[WorkSubmission]:
        stmt = select(TaskRunV2ORM).where(TaskRunV2ORM.id == str(task_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return WorkSubmission(
            id=TaskId(orm.id),
            task_type=orm.task_type,
            state=orm.state,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            payload=json.loads(orm.payload_json) if orm.payload_json else {},
            result=json.loads(orm.result_json) if orm.result_json else None,
            error=orm.error,
            workflow_run_id=WorkflowId(orm.workflow_run_id)
            if orm.workflow_run_id
            else None,
            step_run_id=orm.step_run_id,
            assigned_worker_id=orm.assigned_worker_id,
        )

    async def get_by_id(self, task_id: TaskId) -> Optional[Task]:
        """TaskRepository protocol method."""
        stmt = select(TaskORM).where(TaskORM.id == str(task_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return Task(
            id=TaskId(orm.id),
            prompt=orm.prompt,
            session_id=SessionId(orm.session_id),
            created_at=orm.created_at,
            status=orm.status,
            tags=json.loads(orm.tags_json) if orm.tags_json else [],
        )

    async def save(self, task: Task) -> None:
        """TaskRepository protocol method."""
        from windagent_storage.orm.models import TaskORM

        orm = TaskORM(
            id=str(task.id),
            prompt=task.prompt,
            session_id=str(task.session_id),
            status=task.status.value
            if hasattr(task.status, "value")
            else str(task.status),
            tags_json=json.dumps(task.tags) if task.tags else "[]",
            created_at=task.created_at,
        )
        await self._session.merge(orm)

    async def list_by_session(self, session_id: SessionId) -> List[Task]:
        """TaskRepository protocol method."""
        stmt = select(TaskORM).where(TaskORM.session_id == str(session_id))
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        tasks = []
        for orm in orms:
            tasks.append(
                Task(
                    id=TaskId(orm.id),
                    prompt=orm.prompt,
                    session_id=SessionId(orm.session_id),
                    created_at=orm.created_at,
                    status=orm.status,
                    tags=json.loads(orm.tags_json) if orm.tags_json else [],
                )
            )
        return tasks

    async def claim(
        self, task_id: TaskId, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        """Claim a task for processing."""
        stmt = select(TaskRunV2ORM).where(TaskRunV2ORM.id == str(task_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm or orm.state != "pending":
            return False
        orm.state = "running"
        orm.assigned_worker_id = worker_id
        orm.updated_at = datetime.now(timezone.utc)
        return True

    async def complete(
        self,
        task_id: TaskId,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        stmt = select(TaskRunV2ORM).where(TaskRunV2ORM.id == str(task_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if orm:
            orm.state = "completed" if error is None else "failed"
            orm.result_json = json.dumps(result) if result else None
            orm.error = error
            orm.updated_at = datetime.now(timezone.utc)

    async def list_pending(self, limit: int = 100) -> List[WorkSubmission]:
        stmt = (
            select(TaskRunV2ORM)
            .where(TaskRunV2ORM.state == "pending")
            .order_by(TaskRunV2ORM.created_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        work_items = []
        for orm in orms:
            work_items.append(
                WorkSubmission(
                    id=TaskId(orm.id),
                    task_type=orm.task_type,
                    state=orm.state,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    payload=json.loads(orm.payload_json) if orm.payload_json else {},
                    result=json.loads(orm.result_json) if orm.result_json else None,
                    error=orm.error,
                    workflow_run_id=WorkflowId(orm.workflow_run_id)
                    if orm.workflow_run_id
                    else None,
                    step_run_id=orm.step_run_id,
                    assigned_worker_id=orm.assigned_worker_id,
                )
            )
        return work_items


class SqlOutboxWriter:
    """SQL Implementation for OutboxWriter core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(self, event: EventEnvelope) -> None:
        from windagent_storage.orm.models import OutboxRecordORM
        from windagent_storage.outbox.sql_repository import SqlOutboxRepository
        from windagent_storage.outbox.models import OutboxRecord
        from windagent_core.domain.lifecycle import utc_now
        import uuid

        repo = SqlOutboxRepository(self._session)
        # Use idempotency_key from event metadata if present, or fallback to event_id + aggregate_id + sequence
        metadata_key = (
            event.metadata.get("idempotency_key")
            if (event.metadata and isinstance(event.metadata, dict))
            else None
        )
        dedup_key = (
            metadata_key or f"{event.event_id}:{event.aggregate_id}:{event.sequence}"
        )
        record = OutboxRecord(
            id=f"outbox_{uuid.uuid4().hex[:12]}",
            event_id=str(event.event_id),
            aggregate_id=str(event.aggregate_id),
            aggregate_type=event.aggregate_type or "session",
            event_type=event.event_type,
            payload_json=event.model_dump_json()
            if hasattr(event, "model_dump_json")
            else str(event.payload),
            schema_version=1,
            sequence_number=event.sequence,
            created_at=utc_now(),
            available_at=utc_now(),
            attempt_count=0,
            last_error=None,
            status="pending",
            deduplication_key=dedup_key,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
        )
        await repo.save(record)


class SqlWorkflowRunRepository:
    """SQL Implementation for WorkflowRunRepository core contract."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, workflow_run: WorkflowRun) -> None:
        orm = WorkflowRunV2ORM(
            id=str(workflow_run.id),
            workflow_type=workflow_run.workflow_type,
            state=workflow_run.state.value if workflow_run.state else "pending",
            created_at=workflow_run.created_at,
            updated_at=workflow_run.updated_at,
            payload_json=json.dumps(workflow_run.payload)
            if workflow_run.payload
            else "{}",
            metadata_json=json.dumps(workflow_run.metadata)
            if workflow_run.metadata
            else "{}",
        )
        await self._session.merge(orm)

    async def get(self, workflow_run_id: WorkflowId) -> Optional[WorkflowRun]:
        stmt = select(WorkflowRunV2ORM).where(
            WorkflowRunV2ORM.id == str(workflow_run_id)
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return WorkflowRun(
            id=WorkflowId(orm.id),
            workflow_type=orm.workflow_type,
            state=orm.state,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            payload=json.loads(orm.payload_json) if orm.payload_json else {},
            metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
        )

    async def list_all(self) -> List[WorkflowRun]:
        stmt = select(WorkflowRunV2ORM).order_by(WorkflowRunV2ORM.created_at.desc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        workflows = []
        for orm in orms:
            workflows.append(
                WorkflowRun(
                    id=WorkflowId(orm.id),
                    workflow_type=orm.workflow_type,
                    state=orm.state,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    payload=json.loads(orm.payload_json) if orm.payload_json else {},
                    metadata=json.loads(orm.metadata_json) if orm.metadata_json else {},
                )
            )
        return workflows
