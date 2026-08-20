"""Recovery leader lease port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RecoveryLeaderLeaseRepositoryPort(Protocol):
    """Singleton leader lease acquisition for startup recovery."""

    async def acquire_leader_lease(
        self, leader_id: str, ttl_seconds: float = 30.0
    ) -> bool:
        ...