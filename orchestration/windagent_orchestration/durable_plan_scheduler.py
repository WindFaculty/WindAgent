"""Production scheduler for immutable ``task_plan_versions`` DAGs.

It never consults ``WorkflowEngine._active_runs``.  A claim is persisted with
CAS in ``task_node_runs`` and an optional durable concurrency-group lock before
the orchestration service dispatches a runtime invocation.
"""

from __future__ import annotations

from typing import Any

from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


class DurablePlanScheduler:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def claim_ready_nodes(self, parent_task_id: str | None = None) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            rows = await MultiAgentRepository(session).claim_ready_node_runs(parent_task_id)
            await session.commit()
            return rows

    async def release_node(self, task_node_run_id: str) -> None:
        async with self._session_factory() as session:
            await MultiAgentRepository(session).release_concurrency_lock(task_node_run_id)
            await session.commit()
