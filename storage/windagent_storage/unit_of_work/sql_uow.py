"""
SqlUnitOfWork for WindAgent Storage Layer (Phase 7).
Implements UnitOfWork core contract port for atomic transactions, repository grouping, and transactional outbox.
"""

from __future__ import annotations
import inspect
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.contracts.finalization import (
    CheckpointHook,
    FinalizationCheckpoint,
    FinalizeTaskExecutionRequest,
    FinalizeTaskExecutionResult,
)
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.orm.v2_orchestration_models import TaskRunORM, WorkflowStepRunORM
from windagent_storage.repositories.sql_repositories import (
    SqlSessionRepository,
    SqlWorkflowRepository,
    SqlEventStore,
    SqlOutboxWriter,
    FileArtifactRepository,
    SqlProviderConfigurationRepository,
    SqlWorkRepository,
    SqlWorkflowRunRepository,
)
from windagent_storage.repositories.v2_orchestration_repositories import (
    SqlTaskRunRepository, SqlExecutionLeaseRepository,
    SqlWorkflowCheckpointRepository, SqlCancellationRepository,
    SqlRuntimeExecutionRepository, SqlRecoveryLeaderLeaseRepository
)

# Type alias for protocol compatibility
TaskRepository = SqlWorkRepository
TaskRunRepository = SqlTaskRunRepository


class SqlUnitOfWork:
    """Concrete SqlUnitOfWork implementing windagent_core.contracts.UnitOfWork protocol."""
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_hook: Optional[CheckpointHook] = None,
    ):
        self._session_factory = session_factory
        self._checkpoint_hook = checkpoint_hook
        self.session: Optional[AsyncSession] = None
        
        # Canonical Repositories conforming to core contracts
        self.tasks: TaskRepository = None  # type: ignore
        self.task_runs: SqlTaskRunRepository = None  # type: ignore
        self.workflows: SqlWorkflowRepository = None  # type: ignore
        self.workflow_runs: SqlWorkflowRunRepository = None  # type: ignore
        self.events: SqlEventStore = None  # type: ignore
        self.outbox: SqlOutboxWriter = None  # type: ignore
        self.sessions: SqlSessionRepository = None  # type: ignore
        self.artifacts: FileArtifactRepository = None  # type: ignore
        self.providers: SqlProviderConfigurationRepository = None  # type: ignore
        self.leases: SqlExecutionLeaseRepository = None  # type: ignore
        self.checkpoints: SqlWorkflowCheckpointRepository = None  # type: ignore
        self.cancellations: SqlCancellationRepository = None  # type: ignore
        self.runtime_executions: SqlRuntimeExecutionRepository = None  # type: ignore
        self.recovery_leader_leases: SqlRecoveryLeaderLeaseRepository = None  # type: ignore

        self._pending_outbox_records: List[OutboxRecordORM] = []

    async def __aenter__(self) -> SqlUnitOfWork:
        self.session = self._session_factory()
        
        self.tasks = TaskRepository(self.session)
        self.task_runs = SqlTaskRunRepository(self.session)
        self.workflows = SqlWorkflowRepository(self.session)
        self.workflow_runs = SqlWorkflowRunRepository(self.session)
        self.events = SqlEventStore(self.session)
        self.outbox = SqlOutboxWriter(self.session)
        self.sessions = SqlSessionRepository(self.session)
        self.artifacts = FileArtifactRepository(self.session)
        self.providers = SqlProviderConfigurationRepository(self.session)
        self.leases = SqlExecutionLeaseRepository(self.session)
        self.checkpoints = SqlWorkflowCheckpointRepository(self.session)
        self.cancellations = SqlCancellationRepository(self.session)
        self.runtime_executions = SqlRuntimeExecutionRepository(self.session)
        self.recovery_leader_leases = SqlRecoveryLeaderLeaseRepository(self.session)

        self._pending_outbox_records = []
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        if self.session:
            await self.session.close()

    async def _checkpoint(self, checkpoint: FinalizationCheckpoint) -> None:
        """Internal Phase 5A crash-gate seam used by the storage finalizer.

        With no hook configured this is a strict no-op (zero overhead and
        identical behavior to pre-Phase-5A construction). A configured hook may
        be synchronous or asynchronous; both shapes are awaited/handled here.
        """
        hook = self._checkpoint_hook
        if hook is None:
            return
        result = hook(checkpoint)
        if inspect.isawaitable(result):
            await result

    async def record_outbox_event(self, event: EventEnvelope) -> None:
        """Records an event in both EventStore and Outbox within the current transaction."""
        if not self.session:
            raise RuntimeError("UnitOfWork context not active.")

        # 1. Append to EventStore
        await self.events.append(event)

        # Phase 5A crash gate: after the domain event-store append and before
        # the corresponding outbox write. A crash here must roll back both.
        await self._checkpoint(FinalizationCheckpoint.AFTER_EVENT_WRITE)

        # 2. Append to Transactional Outbox
        await self.outbox.write(event)

    async def list_non_terminal_task_runs(self, batch_size: int) -> List[Dict[str, Any]]:
        """Return non-terminal task runs as plain dicts (recovery scans)."""
        if self.session is None:
            return []
        stmt = (
            select(TaskRunORM)
            .where(TaskRunORM.state.notin_(["completed", "failed", "cancelled"]))
            .limit(batch_size)
        )
        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        return [
            {
                "id": row.id,
                "state": row.state,
                "version": row.version,
                "session_id": row.session_id,
                "project_id": row.project_id,
            }
            for row in rows
        ]

    async def list_in_flight_steps(self, batch_size: int) -> List[Dict[str, Any]]:
        """Return in-flight workflow step runs as plain dicts (recovery scans)."""
        if self.session is None:
            return []
        stmt = (
            select(WorkflowStepRunORM)
            .where(WorkflowStepRunORM.state.in_(["running", "dispatched", "retry_wait"]))
            .limit(batch_size)
        )
        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        return [
            {
                "id": row.id,
                "state": row.state,
                "tool_name": row.tool_name,
                "error": row.error,
                "workflow_run_id": row.workflow_run_id,
            }
            for row in rows
        ]

    async def set_step_state(
        self, step_id: str, state: str, error: Optional[str] = None
    ) -> None:
        """Persist a reconciled workflow step state (recovery scans)."""
        if self.session is None:
            return
        row = await self.session.get(WorkflowStepRunORM, step_id)
        if row is None:
            return
        row.state = state
        if error is not None:
            row.error = error

    async def finalize_task_execution(
        self, request: FinalizeTaskExecutionRequest
    ) -> FinalizeTaskExecutionResult:
        """Executes atomic task execution finalization (Phase 2)."""
        from windagent_storage.services.task_finalizer import TaskFinalizer

        finalizer = TaskFinalizer(self)
        return await finalizer.finalize_task_execution(request)

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
        self._pending_outbox_records.clear()
