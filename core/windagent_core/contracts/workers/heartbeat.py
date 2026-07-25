"""Worker heartbeat persistence port."""

from typing import Protocol, Sequence, runtime_checkable

from windagent_core.contracts.workers.models import WorkerHeartbeat


@runtime_checkable
class WorkerHeartbeatRepository(Protocol):
    async def get_active_workers(self, stale_after_seconds: int) -> Sequence[WorkerHeartbeat]:
        ...

    async def record_heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        ...