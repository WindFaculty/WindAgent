"""
WindAgent Storage Package (V2 Architecture).
SQLAlchemy ORMs, async database connection manager, domain-ORM mappers, repositories, Unit of Work, and transactional outbox.
"""

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import (
    BaseORM, SessionORM, TaskORM, WorkflowRunORM, WorkflowStepORM,
    ExecutionEventORM, OutboxRecordORM, ArtifactRefORM, ProviderConfigORM
)
from windagent_storage.mappers.domain_orm import (
    orm_to_domain_session, domain_to_orm_session,
    orm_to_domain_task, domain_to_orm_task,
    orm_to_domain_step, domain_to_orm_step,
    orm_to_domain_workflow, domain_to_orm_workflow,
    orm_to_domain_event, domain_to_orm_event,
    orm_to_domain_artifact, domain_to_orm_artifact
)
from windagent_storage.repositories.sql_repositories import (
    SqlSessionRepository, SqlTaskRepository, SqlWorkflowRepository,
    SqlEventStore, FileArtifactRepository, SqlProviderConfigurationRepository
)
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_storage.outbox.processor import TransactionalOutboxManager

__version__ = "0.3.0"

__all__ = [
    "DatabaseManager",
    "BaseORM", "SessionORM", "TaskORM", "WorkflowRunORM", "WorkflowStepORM",
    "ExecutionEventORM", "OutboxRecordORM", "ArtifactRefORM", "ProviderConfigORM",
    "orm_to_domain_session", "domain_to_orm_session",
    "orm_to_domain_task", "domain_to_orm_task",
    "orm_to_domain_step", "domain_to_orm_step",
    "orm_to_domain_workflow", "domain_to_orm_workflow",
    "orm_to_domain_event", "domain_to_orm_event",
    "orm_to_domain_artifact", "domain_to_orm_artifact",
    "SqlSessionRepository", "SqlTaskRepository", "SqlWorkflowRepository",
    "SqlEventStore", "FileArtifactRepository", "SqlProviderConfigurationRepository",
    "SqlUnitOfWork", "TransactionalOutboxManager",
]
