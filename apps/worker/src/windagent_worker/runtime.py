"""Phase 7 worker engine: claim, lease, dispatch, validate, and finalize."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from enum import StrEnum
from time import perf_counter

from windagent.kernel.ids import CorrelationId, EntityId
from windagent.kernel.time import Clock, SystemClock
from windagent.platform.events import OutboxPublisher
from windagent.platform.jobs import (
    DurableJobQueue,
    JobEnvelope,
    JobHandlerRegistry,
    JobResultValidationError,
    JobResultValidator,
    JobStatus,
)
from windagent.platform.observability import (
    OperationContext,
    RuntimeTelemetry,
    Telemetry,
    bind_operation_context,
)

from .lease import LeaseGuard


class WorkerTickStatus(StrEnum):
    """Observable outcome of one worker poll cycle."""

    IDLE = "idle"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class WorkerTickReport:
    status: WorkerTickStatus
    job_id: str | None = None
    attempt: int | None = None
    outbox_published: int = 0
    error: str | None = None
    run_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded deterministic exponential retry delay."""

    base_delay_s: float = 1.0
    max_delay_s: float = 60.0

    def __post_init__(self) -> None:
        if self.base_delay_s < 0:
            raise ValueError("base_delay_s must be non-negative")
        if self.max_delay_s < self.base_delay_s:
            raise ValueError("max_delay_s must be at least base_delay_s")

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        multiplier = float(2 ** (attempt - 1))
        return min(self.max_delay_s, self.base_delay_s * multiplier)


class WorkerRuntime:
    """A process-local engine over the durable queue.

    The queue remains the sole authority for ownership and terminal state.
    A result is accepted only after a final exact-token heartbeat and a
    fencing-protected atomic update that writes the outbox event in the same
    transaction.
    """

    def __init__(
        self,
        queue: DurableJobQueue,
        handlers: JobHandlerRegistry,
        *,
        worker_id: str,
        lease_s: float = 30.0,
        heartbeat_interval_s: float = 5.0,
        retry_policy: RetryPolicy | None = None,
        outbox_publisher: OutboxPublisher | None = None,
        clock: Clock | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty text")
        if lease_s <= 0:
            raise ValueError("lease_s must be positive")
        if heartbeat_interval_s <= 0 or heartbeat_interval_s >= lease_s:
            raise ValueError("heartbeat_interval_s must be positive and lower than lease_s")
        self._queue = queue
        self._handlers = handlers
        self._worker_id = worker_id.strip()
        self._lease_s = lease_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._retry_policy = retry_policy or RetryPolicy()
        self._outbox_publisher = outbox_publisher
        self._clock: Clock = clock or SystemClock()
        self._telemetry = telemetry or RuntimeTelemetry("windagent-worker")
        self._validator = JobResultValidator()
        self._lease_guard = LeaseGuard(queue, worker_id=self._worker_id, lease_s=lease_s)
        self._current_job: JobEnvelope | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def current_job_id(self) -> str | None:
        return str(self._current_job.id) if self._current_job is not None else None

    async def run_once(self, *, stop: asyncio.Event | None = None) -> WorkerTickReport:
        """Run one complete poll cycle and return its durable outcome."""
        poll_context = OperationContext.root()
        with bind_operation_context(poll_context):
            poll_span = self._telemetry.start_span(
                "worker.poll", attributes={"worker.id": self._worker_id}
            )
            try:
                await self._queue.recover_expired()
                job = await self._queue.claim_next(
                    worker_id=self._worker_id, lease_s=self._lease_s
                )
                if job is None:
                    published = await self._publish_outbox()
                    self._telemetry.increment_counter(
                        "worker.polls", attributes={"outcome": "idle"}
                    )
                    return WorkerTickReport(
                        WorkerTickStatus.IDLE, outbox_published=published
                    )
                poll_span.set_attribute("worker.poll.outcome", "claimed")
                self._telemetry.increment_counter(
                    "worker.polls", attributes={"outcome": "claimed"}
                )
            except BaseException as error:
                poll_span.record_exception(error)
                self._telemetry.increment_counter(
                    "worker.polls", attributes={"outcome": "error"}
                )
                raise
            finally:
                poll_span.end()

        return await self._run_claimed_job(job, stop=stop)

    async def _run_claimed_job(
        self, job: JobEnvelope, *, stop: asyncio.Event | None
    ) -> WorkerTickReport:
        run_id = str(EntityId.new())
        task_id = str(EntityId.new())
        context = OperationContext.root(
            trace_id=job.trace_id,
            correlation_id=job.correlation_id or CorrelationId.new(),
            causation_id=job.causation_id,
            actor_id=job.actor_id,
            job_id=str(job.id),
            run_id=run_id,
            task_id=task_id,
        )
        started = perf_counter()
        metric_attributes = {"job_type": job.job_type}
        self._current_job = job
        with bind_operation_context(context):
            span = self._telemetry.start_span(
                "worker.job.execute",
                attributes={
                    "job.type": job.job_type,
                    "job.attempt": job.attempt,
                    "worker.id": self._worker_id,
                },
            )
            try:
                report = await self._execute_claimed_job(job, stop=stop)
                report = replace(report, run_id=run_id, task_id=task_id)
                outcome_attributes = {
                    **metric_attributes,
                    "outcome": report.status.value,
                }
                self._telemetry.increment_counter(
                    "worker.jobs", attributes=outcome_attributes
                )
                self._telemetry.observe_histogram(
                    "worker.job.duration_ms",
                    (perf_counter() - started) * 1_000.0,
                    attributes=outcome_attributes,
                )
                self._telemetry.emit_event(
                    "worker.job.completed",
                    attributes={
                        "job_type": job.job_type,
                        "outcome": report.status.value,
                        "attempt": job.attempt,
                    },
                )
                span.set_attribute("job.outcome", report.status.value)
                return report
            except BaseException as error:
                span.record_exception(error)
                self._telemetry.increment_counter(
                    "worker.jobs",
                    attributes={**metric_attributes, "outcome": "error"},
                )
                raise
            finally:
                span.end()
                self._current_job = None

    async def _execute_claimed_job(
        self, job: JobEnvelope, *, stop: asyncio.Event | None
    ) -> WorkerTickReport:
        """Execute a claimed job while the caller owns telemetry context."""
        initial_lease = await self._lease_guard.check_authority(job)
        if not initial_lease.authoritative:
            return self._report(job, WorkerTickStatus.STALE, error="lease authority lost")
        if initial_lease.cancellation_requested:
            finalization = await self._queue.cancel_claim(job, worker_id=self._worker_id)
            return await self._final_report(job, finalization.status)

        if job.deadline is not None and self._clock.now() >= job.deadline:
            return await self._fail(job, "job deadline exceeded", retryable=True)

        handler = self._handlers.get(job.job_type)
        if handler is None:
            return await self._fail(
                job,
                f"no handler registered for job type {job.job_type!r}",
                retryable=False,
            )

        execution = asyncio.create_task(handler.handle(job.payload))
        loop = asyncio.get_running_loop()
        timeout_at = loop.time() + job.timeout_s if job.timeout_s is not None else None
        while not execution.done():
            wait_s = self._heartbeat_interval_s
            if timeout_at is not None:
                wait_s = min(wait_s, max(0.0, timeout_at - loop.time()))
            done, _ = await asyncio.wait({execution}, timeout=wait_s)
            if done:
                break

            if stop is not None and stop.is_set():
                await _cancel_task(execution)
                return await self._fail(job, "worker stopped", retryable=True)
            if timeout_at is not None and loop.time() >= timeout_at:
                await _cancel_task(execution)
                return await self._fail(job, "job execution timed out", retryable=True)
            if job.deadline is not None and self._clock.now() >= job.deadline:
                await _cancel_task(execution)
                return await self._fail(job, "job deadline exceeded", retryable=True)

            lease = await self._lease_guard.heartbeat(job)
            if not lease.authoritative:
                await _cancel_task(execution)
                return self._report(job, WorkerTickStatus.STALE, error="lease authority lost")
            if lease.cancellation_requested:
                await _cancel_task(execution)
                finalization = await self._queue.cancel_claim(
                    job, worker_id=self._worker_id
                )
                return await self._final_report(job, finalization.status)

        try:
            raw_result = execution.result()
        except asyncio.CancelledError:
            return await self._fail(job, "handler cancelled", retryable=True)
        except Exception as error:  # noqa: BLE001 - converted into durable retry state
            return await self._fail(
                job,
                f"{type(error).__name__}: {error}",
                retryable=True,
            )

        authority = await self._lease_guard.check_authority(job)
        if not authority.authoritative:
            return self._report(job, WorkerTickStatus.STALE, error="stale result rejected")
        if authority.cancellation_requested:
            finalization = await self._queue.cancel_claim(job, worker_id=self._worker_id)
            return await self._final_report(job, finalization.status)

        try:
            result = self._validator.validate(raw_result)
        except JobResultValidationError as error:
            return await self._fail(job, str(error), retryable=False)

        finalization = await self._queue.complete(
            job,
            worker_id=self._worker_id,
            result=result,
        )
        if not finalization.accepted:
            return self._report(job, WorkerTickStatus.STALE, error="stale result rejected")
        return await self._final_report(job, finalization.status)

    async def run(
        self,
        *,
        stop: asyncio.Event,
        idle_interval_s: float = 0.25,
    ) -> int:
        """Poll until stopped and return the number of non-idle cycles."""
        if idle_interval_s <= 0:
            raise ValueError("idle_interval_s must be positive")
        processed = 0
        while not stop.is_set():
            report = await self.run_once(stop=stop)
            if report.status == WorkerTickStatus.IDLE:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_interval_s)
                except TimeoutError:
                    pass
            else:
                processed += 1
        return processed

    async def _fail(
        self,
        job: JobEnvelope,
        error: str,
        *,
        retryable: bool,
    ) -> WorkerTickReport:
        finalization = await self._queue.fail(
            job,
            worker_id=self._worker_id,
            error=error,
            retryable=retryable,
            retry_delay_s=self._retry_policy.delay_for(job.attempt),
        )
        if not finalization.accepted:
            return self._report(job, WorkerTickStatus.STALE, error="stale failure rejected")
        return await self._final_report(job, finalization.status, error=error)

    async def _final_report(
        self,
        job: JobEnvelope,
        status: JobStatus,
        *,
        error: str | None = None,
    ) -> WorkerTickReport:
        published = await self._publish_outbox()
        mapping = {
            JobStatus.SUCCEEDED: WorkerTickStatus.SUCCEEDED,
            JobStatus.RETRY_WAIT: WorkerTickStatus.RETRY_SCHEDULED,
            JobStatus.FAILED: WorkerTickStatus.FAILED,
            JobStatus.CANCELLED: WorkerTickStatus.CANCELLED,
        }
        return self._report(
            job,
            mapping.get(status, WorkerTickStatus.STALE),
            outbox_published=published,
            error=error,
        )

    async def _publish_outbox(self) -> int:
        if self._outbox_publisher is None:
            return 0
        report = await self._outbox_publisher.publish_pending()
        return report.published

    @staticmethod
    def _report(
        job: JobEnvelope,
        status: WorkerTickStatus,
        *,
        outbox_published: int = 0,
        error: str | None = None,
    ) -> WorkerTickReport:
        return WorkerTickReport(
            status=status,
            job_id=str(job.id),
            attempt=job.attempt,
            outbox_published=outbox_published,
            error=error,
        )


async def _cancel_task(task: asyncio.Task[object]) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        # The task may have completed with an error between ``done`` and
        # ``cancel``. The caller is already durably finalizing timeout,
        # cancellation, or worker-stop state, so that raced outcome is stale.
        pass
