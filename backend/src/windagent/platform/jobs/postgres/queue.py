"""PostgreSQL durable queue with leases, fencing, retry, and atomic outbox finalization."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId
from windagent.kernel.time import Clock, SystemClock, normalize_utc
from windagent.kernel.types import Version
from windagent.kernel.types.json import JSONValue, thaw_json
from windagent.platform.events import TransactionalOutbox
from windagent.platform.persistence import CheckpointHook, SqlUnitOfWork

from ..contracts import (
    JobFinalization,
    JobLeaseState,
    JobReceipt,
    JobSubmission,
)
from ..envelope import JobEnvelope, JobEventType, JobRecord, JobStatus
from ..result import JobResultValidator
from .schema import job_attempts_table, jobs_table

CHECKPOINT_AFTER_JOB_STATE_WRITE = "after_job_state_write"
_CLAIM_SCAN_LIMIT = 32


class PostgresJobQueue:
    """Canonical SQL job queue; non-PostgreSQL execution is test-only.

    Claims are ordered by priority descending then creation time ascending.
    PostgreSQL uses ``FOR UPDATE SKIP LOCKED``; every dialect also uses a
    guarded update so only one worker can acquire a candidate.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        checkpoint_hook: CheckpointHook | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock: Clock = clock or SystemClock()
        self._checkpoint_hook = checkpoint_hook
        self._validator = JobResultValidator()

    async def submit(self, job: JobSubmission) -> JobReceipt:
        return await self._insert(job, run_at=self._clock.now())

    async def schedule(self, job: JobSubmission, *, run_at: datetime) -> JobReceipt:
        normalized_run_at = normalize_utc(run_at)
        if job.deadline is not None and normalized_run_at > job.deadline:
            raise ValueError("run_at cannot be after the job deadline")
        return await self._insert(job, run_at=normalized_run_at)

    async def _insert(self, job: JobSubmission, *, run_at: datetime) -> JobReceipt:
        if not isinstance(job, JobSubmission):
            raise TypeError("job must be a JobSubmission")
        now = self._clock.now()
        job_id = EntityId.new()

        async with self._session_factory() as session:
            try:
                if job.idempotency_key is not None:
                    existing = await self._find_idempotent(session, job.idempotency_key)
                    if existing is not None:
                        return JobReceipt(EntityId(existing), deduplicated=True)

                await session.execute(
                    insert(jobs_table).values(
                        id=str(job_id),
                        job_type=job.job_type,
                        job_version=int(job.version),
                        payload_json=_json_dump(job.payload),
                        priority=job.priority,
                        attempt_count=0,
                        max_attempts=job.max_attempts,
                        timeout_s=job.timeout_s,
                        deadline=job.deadline,
                        correlation_id=(
                            str(job.correlation_id) if job.correlation_id is not None else None
                        ),
                        causation_id=(
                            str(job.causation_id) if job.causation_id is not None else None
                        ),
                        trace_id=job.trace_id,
                        actor_id=str(job.actor_id) if job.actor_id is not None else None,
                        status=JobStatus.PENDING.value,
                        available_at=normalize_utc(run_at),
                        created_at=now,
                        updated_at=now,
                        lease_generation=0,
                        idempotency_key=job.idempotency_key,
                    )
                )
                await session.commit()
                return JobReceipt(job_id)
            except IntegrityError:
                await session.rollback()
                if job.idempotency_key is None:
                    raise
                existing = await self._find_idempotent(session, job.idempotency_key)
                if existing is None:
                    raise
                return JobReceipt(EntityId(existing), deduplicated=True)

    async def _find_idempotent(self, session: AsyncSession, key: str) -> str | None:
        result = await session.execute(
            select(jobs_table.c.id).where(jobs_table.c.idempotency_key == key)
        )
        value = result.scalar_one_or_none()
        return cast(str | None, value)

    async def claim_next(self, *, worker_id: str, lease_s: float) -> JobEnvelope | None:
        worker = _required_text(worker_id, "worker_id")
        _require_positive(lease_s, "lease_s")
        now = self._clock.now()
        expires_at = now + timedelta(seconds=lease_s)

        async with self._session_factory() as session:
            supports_skip_locked = _supports_skip_locked(session)
            scan = (
                select(jobs_table)
                .where(
                    or_(
                        and_(
                            jobs_table.c.status.in_(
                                (JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value)
                            ),
                            jobs_table.c.available_at <= now,
                        ),
                        and_(
                            jobs_table.c.status == JobStatus.RUNNING.value,
                            jobs_table.c.lease_expires_at < now,
                            jobs_table.c.attempt_count < jobs_table.c.max_attempts,
                        ),
                    )
                )
                .order_by(jobs_table.c.priority.desc(), jobs_table.c.queue_position.asc())
                .limit(1 if supports_skip_locked else _CLAIM_SCAN_LIMIT)
            )
            if supports_skip_locked:
                scan = scan.with_for_update(skip_locked=True)

            rows = (await session.execute(scan)).all()
            for row in rows:
                expired_takeover = row.status == JobStatus.RUNNING.value
                next_attempt = int(row.attempt_count) + 1
                next_generation = int(row.lease_generation) + 1
                fencing_token = (
                    f"job_{row.id}_generation_{next_generation}_{uuid4().hex[:12]}"
                )

                guard = [jobs_table.c.id == row.id]
                if expired_takeover:
                    guard.extend(
                        (
                            jobs_table.c.status == JobStatus.RUNNING.value,
                            jobs_table.c.fencing_token == row.fencing_token,
                            jobs_table.c.lease_expires_at < now,
                        )
                    )
                else:
                    guard.extend(
                        (
                            jobs_table.c.status.in_(
                                (JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value)
                            ),
                            jobs_table.c.available_at <= now,
                        )
                    )

                claim = (
                    update(jobs_table)
                    .where(*guard)
                    .values(
                        status=JobStatus.RUNNING.value,
                        attempt_count=next_attempt,
                        lease_generation=next_generation,
                        claimed_by=worker,
                        fencing_token=fencing_token,
                        lease_expires_at=expires_at,
                        started_at=now,
                        updated_at=now,
                        completed_at=None,
                    )
                )
                outcome = cast("CursorResult[Any]", await session.execute(claim))
                if outcome.rowcount != 1:
                    continue

                if expired_takeover and row.fencing_token:
                    await session.execute(
                        update(job_attempts_table)
                        .where(
                            job_attempts_table.c.job_id == row.id,
                            job_attempts_table.c.fencing_token == row.fencing_token,
                            job_attempts_table.c.status == JobStatus.RUNNING.value,
                        )
                        .values(
                            status="abandoned",
                            finished_at=now,
                            error="lease expired before finalization",
                        )
                    )

                await session.execute(
                    insert(job_attempts_table).values(
                        id=str(uuid4()),
                        job_id=row.id,
                        attempt=next_attempt,
                        worker_id=worker,
                        fencing_token=fencing_token,
                        status=JobStatus.RUNNING.value,
                        started_at=now,
                    )
                )
                await session.commit()
                return _row_to_envelope(
                    row,
                    attempt=next_attempt,
                    fencing_token=fencing_token,
                )

            await session.rollback()
        return None

    async def heartbeat(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        lease_s: float,
    ) -> JobLeaseState:
        worker = _required_text(worker_id, "worker_id")
        _require_positive(lease_s, "lease_s")
        token = _required_fencing_token(job)
        now = self._clock.now()
        expires_at = now + timedelta(seconds=lease_s)
        statement = (
            update(jobs_table)
            .where(
                jobs_table.c.id == str(job.id),
                jobs_table.c.status == JobStatus.RUNNING.value,
                jobs_table.c.claimed_by == worker,
                jobs_table.c.fencing_token == token,
                jobs_table.c.lease_expires_at >= now,
            )
            .values(lease_expires_at=expires_at, updated_at=now)
            .returning(jobs_table.c.cancellation_requested_at)
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
            await session.commit()
        if row is None:
            return JobLeaseState(authoritative=False)
        return JobLeaseState(
            authoritative=True,
            cancellation_requested=row.cancellation_requested_at is not None,
            expires_at=expires_at,
        )

    async def complete(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        result: object,
    ) -> JobFinalization:
        validated = self._validator.validate(result)
        return await self._finalize_claim(
            job,
            worker_id=worker_id,
            requested_status=JobStatus.SUCCEEDED,
            result=validated,
        )

    async def fail(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        error: str,
        retryable: bool,
        retry_delay_s: float,
    ) -> JobFinalization:
        _require_positive_or_zero(retry_delay_s, "retry_delay_s")
        message = _required_text(error, "error")[:8000]
        now = self._clock.now()
        can_retry = (
            retryable
            and job.attempt < job.max_attempts
            and (job.deadline is None or now < job.deadline)
        )
        return await self._finalize_claim(
            job,
            worker_id=worker_id,
            requested_status=(JobStatus.RETRY_WAIT if can_retry else JobStatus.FAILED),
            error=message,
            retry_delay_s=retry_delay_s,
        )

    async def cancel_claim(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
    ) -> JobFinalization:
        return await self._finalize_claim(
            job,
            worker_id=worker_id,
            requested_status=JobStatus.CANCELLED,
            error="cancellation requested",
        )

    async def _finalize_claim(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        requested_status: JobStatus,
        result: JSONValue | None = None,
        error: str | None = None,
        retry_delay_s: float = 0.0,
    ) -> JobFinalization:
        worker = _required_text(worker_id, "worker_id")
        token = _required_fencing_token(job)
        now = self._clock.now()

        async with SqlUnitOfWork(
            self._session_factory,
            checkpoint_hook=self._checkpoint_hook,
        ) as unit_of_work:
            query = select(jobs_table).where(jobs_table.c.id == str(job.id))
            if _supports_skip_locked(unit_of_work.session):
                query = query.with_for_update()
            row = (await unit_of_work.session.execute(query)).first()
            if row is None or not _owns_live_claim(row, worker=worker, token=token, now=now):
                return JobFinalization(False, JobStatus.RUNNING)

            final_status = requested_status
            if row.cancellation_requested_at is not None:
                final_status = JobStatus.CANCELLED
                result = None
                error = "cancellation requested"

            terminal = final_status.terminal
            values: dict[str, object] = {
                "status": final_status.value,
                "updated_at": now,
                "claimed_by": None,
                "fencing_token": None,
                "lease_expires_at": None,
                "last_error": error,
                "result_json": _json_dump(result) if result is not None else None,
                "completed_at": now if terminal else None,
            }
            if final_status == JobStatus.RETRY_WAIT:
                values["available_at"] = now + timedelta(seconds=retry_delay_s)

            statement = (
                update(jobs_table)
                .where(
                    jobs_table.c.id == str(job.id),
                    jobs_table.c.status == JobStatus.RUNNING.value,
                    jobs_table.c.claimed_by == worker,
                    jobs_table.c.fencing_token == token,
                    jobs_table.c.lease_expires_at >= now,
                )
                .values(**values)
            )
            outcome = cast(
                "CursorResult[Any]",
                await unit_of_work.session.execute(statement),
            )
            if outcome.rowcount != 1:
                return JobFinalization(False, JobStatus.RUNNING)

            await unit_of_work.session.execute(
                update(job_attempts_table)
                .where(
                    job_attempts_table.c.job_id == str(job.id),
                    job_attempts_table.c.fencing_token == token,
                    job_attempts_table.c.status == JobStatus.RUNNING.value,
                )
                .values(
                    status=("failed" if final_status == JobStatus.RETRY_WAIT else final_status.value),
                    finished_at=now,
                    error=error,
                )
            )
            await unit_of_work.checkpoint(CHECKPOINT_AFTER_JOB_STATE_WRITE)

            event_type = _event_type_for(final_status)
            payload: dict[str, object] = {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                "status": final_status.value,
            }
            if result is not None:
                payload["result"] = thaw_json(result)
            if error is not None:
                payload["error"] = error
            if final_status == JobStatus.RETRY_WAIT:
                payload["retry_at"] = cast(datetime, values["available_at"]).isoformat()

            outbox = TransactionalOutbox(unit_of_work, clock=self._clock)
            await outbox.record_next(
                EventEnvelope(
                    event_type=event_type.value,
                    aggregate_type="job",
                    aggregate_id=job.id,
                    sequence=0,
                    payload=cast("Mapping[str, JSONValue]", payload),
                    correlation_id=job.correlation_id,
                    causation_id=job.causation_id,
                ),
                deduplication_key=f"job:{job.id}:attempt:{job.attempt}:{event_type.value}",
            )
            await unit_of_work.commit()
            return JobFinalization(
                True,
                final_status,
                retry_scheduled=final_status == JobStatus.RETRY_WAIT,
            )

    async def request_cancel(self, job_id: EntityId) -> bool:
        if not isinstance(job_id, EntityId):
            raise TypeError("job_id must be an EntityId")
        now = self._clock.now()
        async with SqlUnitOfWork(
            self._session_factory,
            checkpoint_hook=self._checkpoint_hook,
        ) as unit_of_work:
            query = select(jobs_table).where(jobs_table.c.id == str(job_id))
            if _supports_skip_locked(unit_of_work.session):
                query = query.with_for_update()
            row = (await unit_of_work.session.execute(query)).first()
            if row is None:
                return False
            status = JobStatus(row.status)
            if status == JobStatus.CANCELLED:
                return True
            if status.terminal:
                return False
            if status == JobStatus.RUNNING:
                await unit_of_work.session.execute(
                    update(jobs_table)
                    .where(
                        jobs_table.c.id == str(job_id),
                        jobs_table.c.status == JobStatus.RUNNING.value,
                    )
                    .values(cancellation_requested_at=now, updated_at=now)
                )
                await unit_of_work.commit()
                return True

            await unit_of_work.session.execute(
                update(jobs_table)
                .where(
                    jobs_table.c.id == str(job_id),
                    jobs_table.c.status.in_(
                        (JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value)
                    ),
                )
                .values(
                    status=JobStatus.CANCELLED.value,
                    cancellation_requested_at=now,
                    completed_at=now,
                    updated_at=now,
                )
            )
            await unit_of_work.checkpoint(CHECKPOINT_AFTER_JOB_STATE_WRITE)
            envelope = _row_to_envelope(row)
            outbox = TransactionalOutbox(unit_of_work, clock=self._clock)
            await outbox.record_next(
                EventEnvelope(
                    event_type=JobEventType.CANCELLED.value,
                    aggregate_type="job",
                    aggregate_id=job_id,
                    sequence=0,
                    payload={
                        "job_id": str(job_id),
                        "job_type": envelope.job_type,
                        "attempt": envelope.attempt,
                        "max_attempts": envelope.max_attempts,
                        "status": JobStatus.CANCELLED.value,
                    },
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.causation_id,
                ),
                deduplication_key=f"job:{job_id}:cancelled",
            )
            await unit_of_work.commit()
        return True

    async def get(self, job_id: EntityId) -> JobRecord | None:
        if not isinstance(job_id, EntityId):
            raise TypeError("job_id must be an EntityId")
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(jobs_table).where(jobs_table.c.id == str(job_id))
                )
            ).first()
        return None if row is None else _row_to_record(row)

    async def recover_expired(self, *, limit: int = 100) -> int:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        now = self._clock.now()
        recovered = 0
        for _ in range(limit):
            async with SqlUnitOfWork(
                self._session_factory,
                checkpoint_hook=self._checkpoint_hook,
            ) as unit_of_work:
                query = (
                    select(jobs_table)
                    .where(
                        jobs_table.c.status == JobStatus.RUNNING.value,
                        jobs_table.c.lease_expires_at < now,
                        or_(
                            jobs_table.c.cancellation_requested_at.is_not(None),
                            jobs_table.c.attempt_count >= jobs_table.c.max_attempts,
                        ),
                    )
                    .order_by(jobs_table.c.lease_expires_at.asc())
                    .limit(1)
                )
                if _supports_skip_locked(unit_of_work.session):
                    query = query.with_for_update(skip_locked=True)
                row = (await unit_of_work.session.execute(query)).first()
                if row is None:
                    break

                status = (
                    JobStatus.CANCELLED
                    if row.cancellation_requested_at is not None
                    else JobStatus.FAILED
                )
                error = (
                    "cancellation requested"
                    if status == JobStatus.CANCELLED
                    else "lease expired after maximum attempts"
                )
                outcome = cast(
                    "CursorResult[Any]",
                    await unit_of_work.session.execute(
                        update(jobs_table)
                        .where(
                            jobs_table.c.id == row.id,
                            jobs_table.c.status == JobStatus.RUNNING.value,
                            jobs_table.c.fencing_token == row.fencing_token,
                            jobs_table.c.lease_expires_at < now,
                        )
                        .values(
                            status=status.value,
                            claimed_by=None,
                            fencing_token=None,
                            lease_expires_at=None,
                            completed_at=now,
                            updated_at=now,
                            last_error=error,
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    continue
                await unit_of_work.session.execute(
                    update(job_attempts_table)
                    .where(
                        job_attempts_table.c.job_id == row.id,
                        job_attempts_table.c.fencing_token == row.fencing_token,
                        job_attempts_table.c.status == JobStatus.RUNNING.value,
                    )
                    .values(status=status.value, finished_at=now, error=error)
                )
                await unit_of_work.checkpoint(CHECKPOINT_AFTER_JOB_STATE_WRITE)
                envelope = _row_to_envelope(row)
                event_type = _event_type_for(status)
                outbox = TransactionalOutbox(unit_of_work, clock=self._clock)
                await outbox.record_next(
                    EventEnvelope(
                        event_type=event_type.value,
                        aggregate_type="job",
                        aggregate_id=envelope.id,
                        sequence=0,
                        payload={
                            "job_id": str(envelope.id),
                            "job_type": envelope.job_type,
                            "attempt": envelope.attempt,
                            "max_attempts": envelope.max_attempts,
                            "status": status.value,
                            "error": error,
                        },
                        correlation_id=envelope.correlation_id,
                        causation_id=envelope.causation_id,
                    ),
                    deduplication_key=(
                        f"job:{envelope.id}:attempt:{envelope.attempt}:{event_type.value}"
                    ),
                )
                await unit_of_work.commit()
                recovered += 1
        return recovered


def _event_type_for(status: JobStatus) -> JobEventType:
    if status == JobStatus.SUCCEEDED:
        return JobEventType.SUCCEEDED
    if status == JobStatus.RETRY_WAIT:
        return JobEventType.RETRY_SCHEDULED
    if status == JobStatus.CANCELLED:
        return JobEventType.CANCELLED
    return JobEventType.FAILED


def _owns_live_claim(row: Any, *, worker: str, token: str, now: datetime) -> bool:
    return bool(
        row.status == JobStatus.RUNNING.value
        and row.claimed_by == worker
        and row.fencing_token == token
        and row.lease_expires_at is not None
        and _as_utc(row.lease_expires_at) >= now
    )


def _required_fencing_token(job: JobEnvelope) -> str:
    if not isinstance(job, JobEnvelope):
        raise TypeError("job must be a JobEnvelope")
    if job.fencing_token is None:
        raise ValueError("claimed job must carry a fencing_token")
    return job.fencing_token


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _require_positive(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_positive_or_zero(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} must be non-negative")


def _supports_skip_locked(session: AsyncSession) -> bool:
    bind = session.bind
    return bind is not None and bind.dialect.name == "postgresql"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _json_dump(value: object) -> str:
    if isinstance(value, (Mapping, tuple)):
        value = thaw_json(cast(JSONValue, value))
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_load(value: str | None) -> JSONValue | None:
    if value is None:
        return None
    return cast(JSONValue, json.loads(value))


def _row_to_envelope(
    row: Any,
    *,
    attempt: int | None = None,
    fencing_token: str | None = None,
) -> JobEnvelope:
    payload = cast(Mapping[str, JSONValue], json.loads(row.payload_json))
    return JobEnvelope(
        id=EntityId(row.id),
        job_type=row.job_type,
        version=Version(row.job_version),
        payload=payload,
        priority=row.priority,
        attempt=row.attempt_count if attempt is None else attempt,
        max_attempts=row.max_attempts,
        timeout_s=row.timeout_s,
        deadline=_as_utc(row.deadline) if row.deadline is not None else None,
        correlation_id=(CorrelationId(row.correlation_id) if row.correlation_id else None),
        causation_id=CausationId(row.causation_id) if row.causation_id else None,
        trace_id=row.trace_id,
        actor_id=ActorId(row.actor_id) if row.actor_id else None,
        fencing_token=(row.fencing_token if fencing_token is None else fencing_token),
    )


def _row_to_record(row: Any) -> JobRecord:
    return JobRecord(
        envelope=_row_to_envelope(row),
        status=JobStatus(row.status),
        available_at=_as_utc(row.available_at),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        lease_expires_at=(
            _as_utc(row.lease_expires_at) if row.lease_expires_at is not None else None
        ),
        completed_at=_as_utc(row.completed_at) if row.completed_at is not None else None,
        cancellation_requested=row.cancellation_requested_at is not None,
        result=_json_load(row.result_json),
        error=row.last_error,
        idempotency_key=row.idempotency_key,
    )
