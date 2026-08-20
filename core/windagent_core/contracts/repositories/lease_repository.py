"""Lease repository port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LeaseRepositoryPort(Protocol):
    """Durable execution lease management port used by orchestration dispatchers."""

    async def acquire_lease(
        self,
        lease_id: str,
        step_run_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: float,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        ...

    async def release_lease(self, lease_id: str, worker_id: str) -> bool:
        ...

    async def reclaim_expired_leases(self) -> List[str]:
        ...