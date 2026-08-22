"""SQL repository composer for the API composition root (Phase 7).

Constructs every concrete SQL repository the API needs for durable command
submission, routing authority, worker status, and Studio read adapters.  The
API never constructs execution runtime or worktree authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.database.sync_factory import make_sync_session_factory
from windagent_storage.repositories.v3_routing_repositories import (
    SQLEndpointBindingRepository,
    SQLModelRouteReceiptRepository,
    SQLProviderRoutingAuditRepository,
)
from windagent_storage.repositories.v3_repositories import (
    SQLEndpointRegistryRepository,
    SQLEndpointStateRepository,
    SQLQuotaStateRepository,
    SQLRouteAttemptRepository,
    SQLRouteLockRepository,
)
from windagent_storage.repositories.worker_status import SqlWorkerHeartbeatRepository
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.repositories.v3_resource_repository import (
    SQLV3ResourceRepository,
)
from windagent_storage.repositories.provider_management_repository import (
    SQLProviderManagementRepository,
)
from windagent_api.composition.studio_storage_adapter import (
    SqlApprovalReadAdapter,
    SqlArtifactReadAdapter,
    SqlEpisodeReadAdapter,
    SqlRevisionReadAdapter,
    SqlRunQueryAdapter,
    SqlEventQueryAdapter,
    SqlSeriesReadAdapter,
)


@dataclass
class RepositoryBundle:
    """Typed result of the repository composer."""

    sync_factory: Any
    binding_repo: SQLEndpointBindingRepository
    audit_repo: SQLProviderRoutingAuditRepository
    lock_repo: SQLRouteLockRepository
    route_receipt_repo: SQLModelRouteReceiptRepository
    provider_management_repo: SQLProviderManagementRepository
    endpoint_registry: SQLEndpointRegistryRepository
    endpoint_state: SQLEndpointStateRepository
    quota_state: SQLQuotaStateRepository
    attempt_log: SQLRouteAttemptRepository
    worker_heartbeat_repo: SqlWorkerHeartbeatRepository
    task_submission: SqlWorkSubmissionAdapter
    studio_task_submission: StudioTaskSubmissionAdapter
    v3_resource_repository_factory: Callable[[Any], Any]
    studio_reads: SqlSeriesReadAdapter
    episodes_repo: SqlEpisodeReadAdapter
    revisions_repo: SqlRevisionReadAdapter
    artifacts_repo: SqlArtifactReadAdapter
    approvals_repo: SqlApprovalReadAdapter
    run_query: SqlRunQueryAdapter
    event_query: SqlEventQueryAdapter


class RepositoryComposer:
    """Constructs the concrete SQL repositories shared by the API services."""

    def compose(self, db: DatabaseManager, db_url: str) -> RepositoryBundle:
        sync_factory = make_sync_session_factory(db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        audit_repo = SQLProviderRoutingAuditRepository(sync_factory())
        lock_repo = SQLRouteLockRepository(sync_factory())
        return RepositoryBundle(
            sync_factory=sync_factory,
            binding_repo=binding_repo,
            audit_repo=audit_repo,
            lock_repo=lock_repo,
            route_receipt_repo=SQLModelRouteReceiptRepository(sync_factory()),
            provider_management_repo=SQLProviderManagementRepository(sync_factory()),
            endpoint_registry=SQLEndpointRegistryRepository(sync_factory()),
            endpoint_state=SQLEndpointStateRepository(sync_factory()),
            quota_state=SQLQuotaStateRepository(sync_factory()),
            attempt_log=SQLRouteAttemptRepository(sync_factory()),
            worker_heartbeat_repo=SqlWorkerHeartbeatRepository(db.session_factory),
            task_submission=SqlWorkSubmissionAdapter(db.session_factory),
            studio_task_submission=StudioTaskSubmissionAdapter(db.session_factory),
            v3_resource_repository_factory=lambda session: SQLV3ResourceRepository(
                session
            ),
            studio_reads=SqlSeriesReadAdapter(db.session_factory),
            episodes_repo=SqlEpisodeReadAdapter(db.session_factory),
            revisions_repo=SqlRevisionReadAdapter(db.session_factory),
            artifacts_repo=SqlArtifactReadAdapter(db.session_factory),
            approvals_repo=SqlApprovalReadAdapter(db.session_factory),
            run_query=SqlRunQueryAdapter(db.session_factory),
            event_query=SqlEventQueryAdapter(db.session_factory),
        )


__all__ = ["RepositoryBundle", "RepositoryComposer"]