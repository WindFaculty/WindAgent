"""Worker submission and status query ports."""

from typing import Protocol, runtime_checkable

from windagent_core.contracts.workers.models import WorkSubmission, WorkerStatus


@runtime_checkable
class WorkSubmissionPort(Protocol):
    async def submit(self, request: WorkSubmission) -> str:
        ...


@runtime_checkable
class WorkerStatusQueryPort(Protocol):
    async def get_status(self, stale_after_seconds: int = 30) -> WorkerStatus:
        ...