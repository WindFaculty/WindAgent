"""Handlers owning the debug job business rules (transport stays dumb)."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.kernel.errors.domain import DomainError
from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId
from windagent.platform.commands import CommandHandler
from windagent.platform.jobs import DurableJobQueue, JobRecord, JobSubmission
from windagent.platform.queries import QueryHandler

from .contracts import (
    CancelDebugJob,
    GetDebugJob,
    SubmitDebugJob,
    SubmitDebugJobResult,
)


@dataclass(slots=True)
class SubmitDebugJobHandler(CommandHandler[SubmitDebugJob, SubmitDebugJobResult]):
    """Validates and submits one debug job to the durable queue."""

    queue: DurableJobQueue

    async def handle(self, command: SubmitDebugJob) -> SubmitDebugJobResult:
        try:
            submission = JobSubmission(
                command.job_type,
                command.payload,
                priority=command.priority,
                max_attempts=command.max_attempts,
                timeout_s=command.timeout_s,
                deadline=command.deadline,
                correlation_id=(
                    CorrelationId(command.correlation_id)
                    if command.correlation_id is not None
                    else None
                ),
                causation_id=(
                    CausationId(command.causation_id)
                    if command.causation_id is not None
                    else None
                ),
                trace_id=command.trace_id,
                actor_id=(
                    ActorId(command.actor_id) if command.actor_id is not None else None
                ),
                idempotency_key=command.idempotency_key,
            )
        except (TypeError, ValueError) as error:
            raise DomainError(str(error), code="validation_error") from error
        receipt = await self.queue.submit(submission)
        return SubmitDebugJobResult(
            job_id=str(receipt.job_id), deduplicated=receipt.deduplicated
        )


@dataclass(slots=True)
class GetDebugJobHandler(QueryHandler[GetDebugJob, JobRecord]):
    """Resolves one debug job record, mapping misses to a domain error."""

    queue: DurableJobQueue

    async def handle(self, query: GetDebugJob) -> JobRecord:
        record = await self.queue.get(_parse_job_id(query.job_id))
        if record is None:
            raise DomainError("job not found", code="not_found")
        return record


@dataclass(slots=True)
class CancelDebugJobHandler(CommandHandler[CancelDebugJob, bool]):
    """Requests durable cancellation, mapping rejections to a conflict."""

    queue: DurableJobQueue

    async def handle(self, command: CancelDebugJob) -> bool:
        accepted = await self.queue.request_cancel(_parse_job_id(command.job_id))
        if not accepted:
            raise DomainError("job cannot be cancelled", code="conflict")
        return True


def _parse_job_id(raw: str) -> EntityId:
    try:
        return EntityId(raw)
    except (TypeError, ValueError) as error:
        raise DomainError("job not found", code="not_found") from error
