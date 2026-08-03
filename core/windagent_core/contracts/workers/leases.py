"""Task lease port definition for lease renewals and releases."""

from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskLeasePort(Protocol):
    """Port for renewing, releasing, and failing task lease locks."""
    async def renew(self, task_id: str, worker_id: str, fencing_token: str, extension_seconds: int = 30) -> bool:
        ...

    async def release(self, task_id: str, worker_id: str, fencing_token: str) -> bool:
        ...

    async def fail(self, task_id: str, worker_id: str, fencing_token: str, error: str) -> bool:
        ...


__all__ = ["TaskLeasePort"]
