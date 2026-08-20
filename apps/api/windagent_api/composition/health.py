"""Health composer for the API composition root (Phase 7).

Constructs the worker heartbeat repository and the worker status query used by
the health/readiness probes.
"""

from __future__ import annotations

from dataclasses import dataclass

from windagent_storage.repositories.worker_status import (
    SqlWorkerHeartbeatRepository,
    SqlWorkerStatusQuery,
)
from windagent_api.composition.repositories import RepositoryBundle


@dataclass
class HealthBundle:
    """Typed result of the health composer."""

    worker_heartbeat_repo: SqlWorkerHeartbeatRepository
    worker_status_query: SqlWorkerStatusQuery


class HealthComposer:
    """Constructs the worker status query for the API health probes."""

    @staticmethod
    def compose(repositories: RepositoryBundle) -> HealthBundle:
        return HealthBundle(
            worker_heartbeat_repo=repositories.worker_heartbeat_repo,
            worker_status_query=SqlWorkerStatusQuery(
                repositories.worker_heartbeat_repo
            ),
        )


__all__ = ["HealthBundle", "HealthComposer"]