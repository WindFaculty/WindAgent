"""Work submission port definition."""

from __future__ import annotations
from typing import Protocol, runtime_checkable

from windagent_core.contracts.workers.models import WorkSubmission


@runtime_checkable
class WorkSubmissionPort(Protocol):
    """Port for submitting work requests into durable task storage."""
    async def submit(self, request: WorkSubmission) -> str:
        ...


__all__ = ["WorkSubmissionPort"]
