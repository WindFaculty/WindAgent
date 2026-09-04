"""Exact-token lease guard used by the worker runtime."""

from __future__ import annotations

from windagent.platform.jobs import DurableJobQueue, JobEnvelope, JobLeaseState


class LeaseGuard:
    """Renew and probe only the lease carried by the claimed envelope."""

    def __init__(self, queue: DurableJobQueue, *, worker_id: str, lease_s: float) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty text")
        if lease_s <= 0:
            raise ValueError("lease_s must be positive")
        self._queue = queue
        self._worker_id = worker_id.strip()
        self._lease_s = lease_s

    async def heartbeat(self, job: JobEnvelope) -> JobLeaseState:
        """Renew the exact fencing token and return its durable state."""
        return await self._queue.heartbeat(
            job,
            worker_id=self._worker_id,
            lease_s=self._lease_s,
        )

    async def check_authority(self, job: JobEnvelope) -> JobLeaseState:
        """Final fencing probe immediately before any terminal mutation."""
        return await self.heartbeat(job)
