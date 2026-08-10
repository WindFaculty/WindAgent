"""StudioTaskSubmissionPort adapter over the durable task queue (Plan A — A4).

Wraps the existing ``SqlWorkSubmissionAdapter`` compatibly: a frozen Studio
task envelope is flattened into the generic ``WorkSubmission`` (tool name =
frozen task type), the envelope survives verbatim in ``parameters`` for the
A5 worker runtime, and the outbox deduplication key makes submission
idempotent per (run, node, attempt).
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.contracts.studio.models import StudioTaskEnvelope
from windagent_core.contracts.studio.ports import StudioTaskSubmissionPort
from windagent_core.contracts.workers.models import WorkSubmission
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter


class StudioTaskSubmissionAdapter(StudioTaskSubmissionPort):
    """Durable queue submission for Studio envelopes with idempotent submits."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._wrapped = SqlWorkSubmissionAdapter(session_factory)

    async def submit(self, envelope: StudioTaskEnvelope) -> str:
        """Submit durably; returns the committed task identity.

        A repeated submit of the same (run, node, attempt) idempotency key
        returns the ORIGINAL task identity without inserting a second queue
        row — the outbox deduplication key is the commit record.
        """
        existing = await self._find_by_idempotency_key(envelope.idempotency_key)
        if existing is not None:
            return existing

        task_id = f"stsk_{uuid.uuid4().hex[:12]}"
        await self._wrapped.submit(
            WorkSubmission(
                prompt=f"[studio] {envelope.task_type.value}",
                task_id=task_id,
                session_id=f"run_{envelope.studio_run_id}",
                workflow_name="studio.story",
                idempotency_key=envelope.idempotency_key,
                tool_name=envelope.task_type.value,
                parameters={
                    "studio_envelope": envelope.to_dict(),
                    "idempotency_key": envelope.idempotency_key,
                    "studio_run_id": str(envelope.studio_run_id),
                    "dag_node_id": envelope.dag_node_id,
                    "attempt": envelope.attempt,
                },
            )
        )
        return task_id

    async def is_duplicate(self, idempotency_key: str) -> bool:
        return await self._find_by_idempotency_key(idempotency_key) is not None

    async def _find_by_idempotency_key(self, idempotency_key: str) -> str | None:
        async with self._session_factory() as session:
            record = await SqlOutboxRepository(session).get_by_deduplication_key(
                idempotency_key
            )
        if record is None:
            return None
        try:
            payload = json.loads(record.payload_json) if record.payload_json else {}
        except (TypeError, ValueError):
            payload = {}
        return payload.get("task_id") if isinstance(payload, dict) else None


__all__ = ["StudioTaskSubmissionAdapter"]
