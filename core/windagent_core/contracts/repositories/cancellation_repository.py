"""Cancellation repository port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CancellationRepositoryPort(Protocol):
    """Durable cancellation request management port."""

    async def request_cancellation(
        self,
        req_id: str,
        target_id: str,
        target_type: str,
        reason: str,
    ) -> None:
        ...

    async def is_cancelled(self, target_id: str) -> bool:
        ...