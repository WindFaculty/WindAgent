"""Frozen worker semantics extracted from WindAgent commit 01695ca4.

The old implementation is a specification only and is never imported. These
oracles capture the behavior of ``SqlDurableTaskQueue`` that Phase 7 must keep:
priority/FIFO ordering, lease-generation takeover, and stale-token rejection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from windagent.platform.jobs import JobSubmission
from windagent.platform.jobs.postgres import PostgresJobQueue
from windagent.platform.persistence import metadata


@dataclass(slots=True)
class ParityClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
async def parity_queue(
    tmp_path: Path,
) -> AsyncIterator[tuple[PostgresJobQueue, ParityClock]]:
    database_path = (tmp_path / "parity.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    clock = ParityClock(datetime(2026, 9, 2, tzinfo=UTC))
    try:
        yield PostgresJobQueue(factory, clock=clock), clock
    finally:
        await engine.dispose()


async def test_frozen_priority_then_fifo_oracle(
    parity_queue: tuple[PostgresJobQueue, ParityClock],
) -> None:
    queue, _ = parity_queue
    first = await queue.submit(JobSubmission("parity", {"order": 1}, priority=5))
    await queue.submit(JobSubmission("parity", {"order": 2}, priority=1))
    await queue.submit(JobSubmission("parity", {"order": 3}, priority=5))

    claimed = await queue.claim_next(worker_id="parity-worker", lease_s=30)

    assert claimed is not None
    assert claimed.id == first.job_id
    assert claimed.payload["order"] == 1


async def test_frozen_lease_takeover_and_fencing_oracle(
    parity_queue: tuple[PostgresJobQueue, ParityClock],
) -> None:
    queue, clock = parity_queue
    await queue.submit(JobSubmission("parity", max_attempts=2))
    generation_one = await queue.claim_next(worker_id="old-worker", lease_s=5)
    assert generation_one is not None

    clock.advance(6)
    generation_two = await queue.claim_next(worker_id="new-worker", lease_s=5)
    assert generation_two is not None

    late = await queue.complete(generation_one, worker_id="old-worker", result={})
    current = await queue.complete(generation_two, worker_id="new-worker", result={})

    assert generation_one.attempt == 1
    assert generation_two.attempt == 2
    assert generation_one.fencing_token != generation_two.fencing_token
    assert late.accepted is False
    assert current.accepted is True
