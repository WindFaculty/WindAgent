"""Explicit storage infrastructure factory (Architecture V3 Phase B hardening).

This module is the SINGLE allowlisted construction point for session-bound
concrete repository adapters inside the storage package. Infrastructure may
DEFINE concrete adapters anywhere, but instantiating them for wiring happens
here (or in an application composition root) so the dependency direction
stays auditable:

    composition root / factory  ->  concrete adapter  ->  core port

Unit-of-work implementations compose their per-session repositories through
these factories instead of hard-instantiating adapter classes inline.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_storage.migrations.backup_manager import BackupManager
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_storage.repositories.sql_repositories import (
    FileArtifactRepository,
    SqlEventStore,
    SqlOutboxWriter,
    SqlProviderConfigurationRepository,
    SqlSessionRepository,
    SqlWorkRepository,
    SqlWorkflowRepository,
    SqlWorkflowRunRepository,
)
from windagent_storage.repositories.v2_orchestration_repositories import (
    SqlCancellationRepository,
    SqlExecutionLeaseRepository,
    SqlMemoryRecordRepository,
    SqlRecoveryLeaderLeaseRepository,
    SqlRuntimeExecutionRepository,
    SqlTaskRunRepository,
    SqlWorkflowCheckpointRepository,
)
from windagent_storage.repositories.v3_routing_repositories import (
    SQLEndpointBindingRepository,
)
from windagent_storage.studio.repositories import (
    SqlApprovalRepository,
    SqlEpisodeRepository,
    SqlSeriesProjectRepository,
    SqlStoryArtifactRepository,
    SqlStudioEventRepository,
    SqlStudioRevisionRepository,
    SqlStudioRunRepository,
)
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.video_production.repositories import (
    IdempotencyRepository,
    ProductionEventRepository,
    ProductionProjectRepository,
    WorkspaceReadModelRepository,
)


def create_backup_manager(backup_root: Optional[str] = None) -> BackupManager:
    """Migration backup authority (storage-internal wiring)."""
    if backup_root:
        return BackupManager(backup_root)
    return BackupManager()


def create_multi_agent_repository(session: AsyncSession) -> MultiAgentRepository:
    return MultiAgentRepository(session)


def create_sql_endpoint_binding_repository(
    session: AsyncSession,
) -> SQLEndpointBindingRepository:
    return SQLEndpointBindingRepository(session)


def create_sql_memory_record_repository(
    session: AsyncSession,
) -> SqlMemoryRecordRepository:
    return SqlMemoryRecordRepository(session)


def create_sql_work_submission_adapter(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    dedup_prefix: str = "studio_submit",
) -> SqlWorkSubmissionAdapter:
    return SqlWorkSubmissionAdapter(session_factory, dedup_prefix=dedup_prefix)


def create_production_project_repository(
    session: AsyncSession,
) -> ProductionProjectRepository:
    return ProductionProjectRepository(session)


def create_idempotency_repository(session: AsyncSession) -> IdempotencyRepository:
    return IdempotencyRepository(session)


def create_production_event_repository(
    session: AsyncSession,
) -> ProductionEventRepository:
    return ProductionEventRepository(session)


def create_workspace_read_model_repository(
    session: AsyncSession,
) -> WorkspaceReadModelRepository:
    return WorkspaceReadModelRepository(session)


def create_sql_outbox_repository(session: AsyncSession) -> SqlOutboxRepository:
    return SqlOutboxRepository(session)


def create_sql_outbox_writer(session: AsyncSession) -> SqlOutboxWriter:
    return SqlOutboxWriter(session)


def create_sql_workflow_repository(session: AsyncSession) -> SqlWorkflowRepository:
    return SqlWorkflowRepository(session)


def create_sql_event_store(session: AsyncSession) -> SqlEventStore:
    return SqlEventStore(session)


def create_sql_episode_repository(session: AsyncSession) -> SqlEpisodeRepository:
    return SqlEpisodeRepository(session)


def create_sql_session_repository(session: AsyncSession) -> SqlSessionRepository:
    return SqlSessionRepository(session)


def create_sql_work_repository(session: AsyncSession) -> SqlWorkRepository:
    return SqlWorkRepository(session)


def create_sql_workflow_run_repository(session: AsyncSession) -> SqlWorkflowRunRepository:
    return SqlWorkflowRunRepository(session)


def create_file_artifact_repository(session: AsyncSession) -> FileArtifactRepository:
    return FileArtifactRepository(session)


def create_sql_provider_configuration_repository(
    session: AsyncSession,
) -> SqlProviderConfigurationRepository:
    return SqlProviderConfigurationRepository(session)


def create_sql_task_run_repository(session: AsyncSession) -> SqlTaskRunRepository:
    return SqlTaskRunRepository(session)


def create_sql_execution_lease_repository(session: AsyncSession) -> SqlExecutionLeaseRepository:
    return SqlExecutionLeaseRepository(session)


def create_sql_workflow_checkpoint_repository(
    session: AsyncSession,
) -> SqlWorkflowCheckpointRepository:
    return SqlWorkflowCheckpointRepository(session)


def create_sql_cancellation_repository(session: AsyncSession) -> SqlCancellationRepository:
    return SqlCancellationRepository(session)


def create_sql_runtime_execution_repository(session: AsyncSession) -> SqlRuntimeExecutionRepository:
    return SqlRuntimeExecutionRepository(session)


def create_sql_recovery_leader_lease_repository(
    session: AsyncSession,
) -> SqlRecoveryLeaderLeaseRepository:
    return SqlRecoveryLeaderLeaseRepository(session)


def create_sql_series_project_repository(session: AsyncSession) -> SqlSeriesProjectRepository:
    return SqlSeriesProjectRepository(session)


def create_sql_studio_revision_repository(session: AsyncSession) -> SqlStudioRevisionRepository:
    return SqlStudioRevisionRepository(session)


def create_sql_story_artifact_repository(session: AsyncSession) -> SqlStoryArtifactRepository:
    return SqlStoryArtifactRepository(session)


def create_sql_approval_repository(session: AsyncSession) -> SqlApprovalRepository:
    return SqlApprovalRepository(session)


def create_sql_studio_run_repository(session: AsyncSession) -> SqlStudioRunRepository:
    return SqlStudioRunRepository(session)


def create_sql_studio_run_node_repository(session: AsyncSession) -> SqlStudioRunNodeRepository:
    return SqlStudioRunNodeRepository(session)


def create_sql_studio_event_repository(session: AsyncSession) -> SqlStudioEventRepository:
    return SqlStudioEventRepository(session)


__all__ = [
    "create_backup_manager",
    "create_file_artifact_repository",
    "create_idempotency_repository",
    "create_multi_agent_repository",
    "create_production_event_repository",
    "create_production_project_repository",
    "create_sql_approval_repository",
    "create_sql_cancellation_repository",
    "create_sql_endpoint_binding_repository",
    "create_sql_episode_repository",
    "create_sql_event_store",
    "create_sql_execution_lease_repository",
    "create_sql_memory_record_repository",
    "create_sql_outbox_repository",
    "create_sql_outbox_writer",
    "create_sql_provider_configuration_repository",
    "create_sql_recovery_leader_lease_repository",
    "create_sql_runtime_execution_repository",
    "create_sql_series_project_repository",
    "create_sql_session_repository",
    "create_sql_studio_event_repository",
    "create_sql_studio_revision_repository",
    "create_sql_studio_run_node_repository",
    "create_sql_studio_run_repository",
    "create_sql_task_run_repository",
    "create_sql_workflow_checkpoint_repository",
    "create_sql_workflow_repository",
    "create_sql_workflow_run_repository",
    "create_sql_work_repository",
    "create_sql_work_submission_adapter",
    "create_workspace_read_model_repository",
]
