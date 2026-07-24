"""
SqlUnitOfWork for WindAgent Storage Layer (Phase 7).
Implements UnitOfWork core contract port for atomic transactions, repository grouping, and transactional outbox.
"""

from __future__ import annotations
import json
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.domain.types import EventId
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.repositories.sql_repositories import (
    SqlSessionRepository, SqlTaskRepository, SqlWorkflowRepository, SqlWorkflowRunRepository,
    SqlEventStore, SqlOutboxWriter, FileArtifactRepository, SqlProviderConfigurationRepository
)
from windagent_storage.repositories.v2_orchestration_repositories import (
    SqlTaskRunRepository, SqlExecutionLeaseRepository,
    SqlWorkflowCheckpointRepository, SqlCancellationRepository,
    SqlRuntimeExecutionRepository, SqlRecoveryLeaderLeaseRepository
)


class SqlUnitOfWork:
    """Concrete SqlUnitOfWork implementing windagent_core.contracts.UnitOfWork protocol."""
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        
        # Canonical Repositories conforming to core contracts
        self.tasks: SqlTaskRepository = None  # type: ignore
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
        
        self.tasks = SqlTaskRepository(self.session)
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

    async def record_outbox_event(self, event: EventEnvelope) -> None:
        """Records an event in both EventStore and Outbox within the current transaction."""
        if not self.session:
            raise RuntimeError("UnitOfWork context not active.")

        # 1. Append to EventStore
        await self.events.append(event)

        # 2. Append to Transactional Outbox
        await self.outbox.write(event)

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
        self._pending_outbox_records.clear()
