"""Durable repository for the canonical multi-agent aggregates.

The Phase-1 aggregate tables are intentionally schema-first.  This repository
is their only Phase-2 persistence boundary, keeping SQL and transaction rules
out of API handlers and the orchestrator service.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


LIVE_RUN_STATUSES = ("dispatching", "running")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MultiAgentRepository:
    """Persistence operations for Conversation through AgentRun.

    All methods only stage work on the supplied ``AsyncSession``.  The caller
    owns the transaction boundary, which is critical when a goal creates a
    parent task, immutable plan, agents, sessions, and runs together.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_conversation(
        self, conversation_id: str, title: str | None = None
    ) -> None:
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO conversations
                (conversation_id, title, status, metadata_json, last_event_sequence, created_at, updated_at)
                VALUES (:id, :title, 'active', '{}', 0, :now, :now)
                ON CONFLICT(conversation_id) DO NOTHING
                """
            ),
            {"id": conversation_id, "title": title, "now": now},
        )

    async def get_or_create_orchestrator(
        self, conversation_id: str, agent_instance_id: str, agent_session_id: str
    ) -> tuple[str, str, bool]:
        existing = (
            await self._session.execute(
                text(
                    """
                    SELECT ai.agent_instance_id, s.agent_session_id
                    FROM agent_instances ai
                    JOIN agent_sessions s ON s.agent_instance_id = ai.agent_instance_id
                    WHERE ai.conversation_id = :conversation_id
                      AND ai.agent_type = 'orchestrator'
                    ORDER BY ai.created_at ASC
                    LIMIT 1
                    """
                ),
                {"conversation_id": conversation_id},
            )
        ).mappings().first()
        if existing:
            return str(existing["agent_instance_id"]), str(existing["agent_session_id"]), False

        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO agent_instances
                (agent_instance_id, conversation_id, agent_type, status, created_at, updated_at)
                VALUES (:id, :conversation_id, 'orchestrator', 'active', :now, :now)
                """
            ),
            {"id": agent_instance_id, "conversation_id": conversation_id, "now": now},
        )
        await self._session.execute(
            text(
                """
                INSERT INTO agent_sessions
                (agent_session_id, agent_instance_id, windagent_session_id, status, version, created_at, updated_at)
                VALUES (:id, :agent_instance_id, :windagent_session_id, 'idle', 1, :now, :now)
                """
            ),
            {
                "id": agent_session_id,
                "agent_instance_id": agent_instance_id,
                "windagent_session_id": f"orchestrator:{conversation_id}",
                "now": now,
            },
        )
        return agent_instance_id, agent_session_id, True

    async def create_parent_task(
        self, parent_task_id: str, conversation_id: str, objective: str
    ) -> None:
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO parent_tasks
                (parent_task_id, conversation_id, objective, status, created_at, updated_at)
                VALUES (:id, :conversation_id, :objective, 'running', :now, :now)
                """
            ),
            {"id": parent_task_id, "conversation_id": conversation_id, "objective": objective, "now": now},
        )

    async def create_plan(
        self,
        plan_version_id: str,
        parent_task_id: str,
        dag: Mapping[str, Any],
    ) -> None:
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO task_plan_versions
                (plan_version_id, parent_task_id, version, dag_json, created_at)
                VALUES (:id, :parent_task_id, 1, :dag_json, :now)
                """
            ),
            {"id": plan_version_id, "parent_task_id": parent_task_id, "dag_json": json.dumps(dag), "now": now},
        )
        await self._session.execute(
            text(
                """
                UPDATE parent_tasks
                SET active_plan_version_id = :plan_version_id, updated_at = :now
                WHERE parent_task_id = :parent_task_id
                """
            ),
            {"plan_version_id": plan_version_id, "parent_task_id": parent_task_id, "now": now},
        )

    async def revision_context(
        self,
        *,
        conversation_id: str,
        parent_task_id: str,
    ) -> dict[str, Any] | None:
        """Return the durable active-plan identity before an append-only revision.

        The caller sends that identity back as a compare-and-swap precondition,
        so a stale editor cannot silently replace a newer plan revision.
        """
        result = await self._session.execute(
            text(
                """
                SELECT pt.objective, pt.active_plan_version_id, pv.version
                FROM parent_tasks pt
                LEFT JOIN task_plan_versions pv
                  ON pv.plan_version_id = pt.active_plan_version_id
                WHERE pt.parent_task_id = :parent_task_id
                  AND pt.conversation_id = :conversation_id
                  AND pt.status = 'running'
                """
            ),
            {"parent_task_id": parent_task_id, "conversation_id": conversation_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def create_plan_revision(
        self,
        *,
        plan_version_id: str,
        parent_task_id: str,
        conversation_id: str,
        base_plan_version_id: str,
        version: int,
        dag: Mapping[str, Any],
    ) -> bool:
        """Append a plan snapshot and atomically make it active.

        Existing AgentRun/TaskNodeRun rows keep their own ``plan_version_id``.
        They are deliberately never rewritten by a plan edit.
        """
        now = utc_now()
        switched = await self._session.execute(
            text(
                """
                UPDATE parent_tasks
                SET active_plan_version_id = :plan_version_id, updated_at = :now
                WHERE parent_task_id = :parent_task_id
                  AND conversation_id = :conversation_id
                  AND status = 'running'
                  AND active_plan_version_id = :base_plan_version_id
                """
            ),
            {
                "plan_version_id": plan_version_id,
                "parent_task_id": parent_task_id,
                "conversation_id": conversation_id,
                "base_plan_version_id": base_plan_version_id,
                "now": now,
            },
        )
        if switched.rowcount != 1:
            return False

        await self._session.execute(
            text(
                """
                INSERT INTO task_plan_versions
                (plan_version_id, parent_task_id, version, dag_json, created_at)
                VALUES (:id, :parent_task_id, :version, :dag_json, :now)
                """
            ),
            {
                "id": plan_version_id,
                "parent_task_id": parent_task_id,
                "version": version,
                "dag_json": json.dumps(dag),
                "now": now,
            },
        )
        return True

    async def list_plan_versions(
        self,
        *,
        conversation_id: str,
        parent_task_id: str,
    ) -> list[dict[str, Any]]:
        """Return every immutable DAG snapshot for one parent task."""
        result = await self._session.execute(
            text(
                """
                SELECT pv.plan_version_id, pv.version, pv.dag_json, pv.created_at,
                       pt.parent_task_id, pt.objective, pt.active_plan_version_id
                FROM task_plan_versions pv
                JOIN parent_tasks pt ON pt.parent_task_id = pv.parent_task_id
                WHERE pt.parent_task_id = :parent_task_id
                  AND pt.conversation_id = :conversation_id
                ORDER BY pv.version ASC, pv.created_at ASC
                """
            ),
            {"parent_task_id": parent_task_id, "conversation_id": conversation_id},
        )
        snapshots: list[dict[str, Any]] = []
        for row in result.mappings().all():
            created_at = row["created_at"]
            snapshots.append(
                {
                "plan_version_id": str(row["plan_version_id"]),
                "version": int(row["version"]),
                "parent_task_id": str(row["parent_task_id"]),
                "objective": str(row["objective"]),
                "dag": json.loads(row["dag_json"] or "{}"),
                "is_active": str(row["plan_version_id"]) == str(row["active_plan_version_id"]),
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
                }
            )
        return snapshots

    async def create_nodes_and_edges(
        self,
        plan_version_id: str,
        nodes: Iterable[Mapping[str, Any]],
        edges: Iterable[Mapping[str, Any]],
    ) -> None:
        now = utc_now()
        for node in nodes:
            await self._session.execute(
                text(
                    """
                    INSERT INTO task_nodes
                    (node_id, plan_version_id, position, agent_type, tool_name, params_json,
                     concurrency_group, created_at)
                    VALUES (:node_id, :plan_version_id, :position, :agent_type, 'agent_run',
                            :params_json, :concurrency_group, :now)
                    """
                ),
                {
                    "node_id": node["node_id"],
                    "plan_version_id": plan_version_id,
                    "position": node["position"],
                    "agent_type": node["agent_type"],
                    "params_json": json.dumps({"objective": node["objective"]}),
                    "concurrency_group": node.get("concurrency_group"),
                    "now": now,
                },
            )
        for edge in edges:
            await self._session.execute(
                text(
                    """
                    INSERT INTO task_edges (edge_id, plan_version_id, from_node_id, to_node_id)
                    VALUES (:edge_id, :plan_version_id, :from_node_id, :to_node_id)
                    """
                ),
                {"plan_version_id": plan_version_id, **edge},
            )

    async def create_agent_run_bundle(
        self,
        *,
        agent_instance_id: str,
        agent_session_id: str,
        agent_run_id: str,
        task_node_run_id: str,
        windagent_session_id: str,
        conversation_id: str,
        parent_task_id: str,
        plan_version_id: str,
        node_id: str,
        agent_type: str,
        concurrency_group: str | None,
        dependency_node_ids: Iterable[str] = (),
    ) -> None:
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO agent_instances
                (agent_instance_id, conversation_id, parent_task_id, agent_type, status, assigned_node_id,
                 created_at, updated_at)
                VALUES (:id, :conversation_id, :parent_task_id, :agent_type, 'queued', :node_id, :now, :now)
                """
            ),
            {
                "id": agent_instance_id,
                "conversation_id": conversation_id,
                "parent_task_id": parent_task_id,
                "agent_type": agent_type,
                "node_id": node_id,
                "now": now,
            },
        )
        await self._session.execute(
            text(
                """
                INSERT INTO agent_sessions
                (agent_session_id, agent_instance_id, windagent_session_id, status, version, created_at, updated_at)
                VALUES (:id, :agent_instance_id, :windagent_session_id, 'queued', 1, :now, :now)
                """
            ),
            {
                "id": agent_session_id,
                "agent_instance_id": agent_instance_id,
                "windagent_session_id": windagent_session_id,
                "now": now,
            },
        )
        await self._session.execute(
            text(
                """
                INSERT INTO task_node_runs
                (task_node_run_id, plan_version_id, node_id, parent_task_id, state, version,
                 facts_json, dependency_state_json, retry_state_json, routing_snapshot_json,
                 concurrency_group, created_at, updated_at)
                VALUES (:id, :plan_version_id, :node_id, :parent_task_id, 'queued', 1,
                        '{}', :dependency_state, :retry_state, '{}', :concurrency_group, :now, :now)
                """
            ),
            {
                "id": task_node_run_id,
                "plan_version_id": plan_version_id,
                "node_id": node_id,
                "parent_task_id": parent_task_id,
                "dependency_state": json.dumps(
                    {"depends_on": list(dependency_node_ids), "status": "waiting"}
                ),
                "retry_state": json.dumps({"attempt": 0, "max_attempts": 3}),
                "concurrency_group": concurrency_group,
                "now": now,
            },
        )
        await self._session.execute(
            text(
                """
                INSERT INTO agent_runs
                (agent_run_id, agent_instance_id, agent_session_id, parent_task_id, plan_version_id,
                 task_node_run_id, status, routing_snapshot_json, version, created_at, updated_at)
                VALUES (:id, :agent_instance_id, :agent_session_id, :parent_task_id, :plan_version_id,
                :task_node_run_id, 'queued', '{}', 1, :now, :now)
                """
            ),
            {
                "id": agent_run_id,
                "agent_instance_id": agent_instance_id,
                "agent_session_id": agent_session_id,
                "parent_task_id": parent_task_id,
                "plan_version_id": plan_version_id,
                "task_node_run_id": task_node_run_id,
                "now": now,
            },
        )

    async def record_dispatch(
        self,
        *,
        agent_run_id: str,
        agent_instance_id: str,
        agent_session_id: str,
        runtime_handle_id: str,
        runtime_run_id: str,
        fencing_token: str,
        routing_snapshot: Mapping[str, Any],
    ) -> None:
        now = utc_now()
        snapshot = json.dumps(routing_snapshot)
        canonical_model_id = routing_snapshot.get("canonical_model_id")
        await self._session.execute(
            text(
                """
                UPDATE agent_runs
                SET runtime_handle_id=:handle_id, runtime_run_id=:runtime_run_id,
                    runtime_locator=:runtime_locator, fencing_token=:fencing_token,
                    routing_snapshot_json=:snapshot,
                    status='running', version=version+1, updated_at=:now
                WHERE agent_run_id=:agent_run_id AND status='dispatching'
                """
            ),
            {
                "handle_id": runtime_handle_id,
                "runtime_run_id": runtime_run_id,
                "runtime_locator": f"runtime://{runtime_run_id}",
                "fencing_token": fencing_token,
                "snapshot": snapshot,
                "now": now,
                "agent_run_id": agent_run_id,
            },
        )
        await self._session.execute(
            text(
                """
                UPDATE agent_sessions
                SET runtime_locator=:runtime_locator, hermes_run_id=:runtime_run_id,
                    status='running', version=version+1, updated_at=:now
                WHERE agent_session_id=:agent_session_id
                """
            ),
            {"runtime_locator": f"runtime://{runtime_run_id}", "runtime_run_id": runtime_run_id,
             "now": now, "agent_session_id": agent_session_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE task_node_runs
                SET state='running', routing_snapshot_json=:snapshot,
                    version=version+1, updated_at=:now
                WHERE task_node_run_id=(
                    SELECT task_node_run_id FROM agent_runs WHERE agent_run_id=:agent_run_id
                ) AND state='dispatching'
                """
            ),
            {"snapshot": snapshot, "now": now, "agent_run_id": agent_run_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE agent_instances
                SET status='running', canonical_model_id=:canonical_model_id, updated_at=:now
                WHERE agent_instance_id=:agent_instance_id
                """
            ),
            {
                "now": now,
                "canonical_model_id": canonical_model_id,
                "agent_instance_id": agent_instance_id,
            },
        )

    async def record_dispatch_failure(self, agent_run_id: str, reason: str) -> None:
        now = utc_now()
        await self._session.execute(
            text(
                """
                UPDATE agent_runs
                SET status='failed', version=version+1, updated_at=:now,
                    routing_snapshot_json=:snapshot
                WHERE agent_run_id=:agent_run_id AND status='dispatching'
                """
            ),
            {
                "now": now,
                "snapshot": json.dumps({"dispatch_error": reason}),
                "agent_run_id": agent_run_id,
            },
        )
        await self._session.execute(
            text(
                """
                UPDATE task_node_runs
                SET state='failed', version=version+1, updated_at=:now
                WHERE task_node_run_id=(
                    SELECT task_node_run_id FROM agent_runs WHERE agent_run_id=:agent_run_id
                ) AND state='dispatching'
                """
            ),
            {"now": now, "agent_run_id": agent_run_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE agent_sessions SET status='failed', version=version+1, updated_at=:now
                WHERE agent_session_id=(
                    SELECT agent_session_id FROM agent_runs WHERE agent_run_id=:agent_run_id
                )
                """
            ),
            {"now": now, "agent_run_id": agent_run_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE agent_instances SET status='failed', updated_at=:now
                WHERE agent_instance_id=(
                    SELECT agent_instance_id FROM agent_runs WHERE agent_run_id=:agent_run_id
                )
                """
            ),
            {"now": now, "agent_run_id": agent_run_id},
        )

    async def claim_ready_node_runs(
        self, parent_task_id: str | None = None
    ) -> list[dict[str, Any]]:
        """CAS-claim due DAG nodes whose pinned parents all completed.

        The query uses the run's ``plan_version_id`` exclusively; a later plan
        version cannot affect an already-running ParentTask.  Group locks are
        inserted before the state transition and released if a competing
        scheduler wins the CAS.
        """
        now = utc_now()
        parent_clause = ""
        params: dict[str, Any] = {"now": now}
        if parent_task_id is not None:
            parent_clause = "AND tnr.parent_task_id=:parent_task_id"
            params["parent_task_id"] = parent_task_id
        rows = await self._session.execute(
            text(
                """
                SELECT tnr.task_node_run_id, tnr.parent_task_id, tnr.plan_version_id,
                       tnr.node_id, tnr.version, tnr.concurrency_group,
                       tnr.dependency_state_json,
                       tn.agent_type, tn.params_json,
                       ar.agent_run_id, ar.agent_instance_id, ar.agent_session_id,
                       aps.windagent_session_id,
                       ai.conversation_id
                FROM task_node_runs tnr
                JOIN task_nodes tn ON tn.plan_version_id=tnr.plan_version_id
                                  AND tn.node_id=tnr.node_id
                JOIN agent_runs ar ON ar.task_node_run_id=tnr.task_node_run_id
                JOIN agent_sessions aps ON aps.agent_session_id=ar.agent_session_id
                JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                WHERE tnr.state IN ('queued', 'retry_wait')
                  AND ar.status='queued'
                  AND (tnr.next_retry_at IS NULL OR tnr.next_retry_at <= :now)
                  """
                + parent_clause
                +
                """
                  AND NOT EXISTS (
                    SELECT 1
                    FROM task_edges edge
                    LEFT JOIN task_node_runs parent_run
                      ON parent_run.plan_version_id=tnr.plan_version_id
                     AND parent_run.parent_task_id=tnr.parent_task_id
                     AND parent_run.node_id=edge.from_node_id
                    WHERE edge.plan_version_id=tnr.plan_version_id
                      AND edge.to_node_id=tnr.node_id
                      AND (parent_run.task_node_run_id IS NULL OR parent_run.state != 'completed')
                  )
                ORDER BY tn.position ASC, tnr.created_at ASC
                """,
            ),
            params,
        )
        claimed: list[dict[str, Any]] = []
        for raw in rows.mappings().all():
            row = dict(raw)
            lock_acquired = await self._try_acquire_concurrency_lock(row, now)
            if not lock_acquired:
                continue
            update_result = await self._session.execute(
                text(
                    """
                    UPDATE task_node_runs
                    SET state='dispatching', dependency_state_json=:dependency_state,
                        version=version+1, updated_at=:now
                    WHERE task_node_run_id=:task_node_run_id AND version=:version
                      AND state IN ('queued', 'retry_wait')
                    """
                ),
                {
                    "now": now,
                    "task_node_run_id": row["task_node_run_id"],
                    "version": row["version"],
                    "dependency_state": json.dumps(
                        {
                            **json.loads(row["dependency_state_json"] or "{}"),
                            "status": "ready",
                            "resolved_at": now.isoformat(),
                        }
                    ),
                },
            )
            if update_result.rowcount != 1:
                await self.release_concurrency_lock(str(row["task_node_run_id"]))
                continue
            run_result = await self._session.execute(
                text(
                    """
                    UPDATE agent_runs
                    SET status='dispatching', version=version+1, updated_at=:now
                    WHERE agent_run_id=:agent_run_id AND status='queued'
                    """
                ),
                {"now": now, "agent_run_id": row["agent_run_id"]},
            )
            if run_result.rowcount != 1:
                await self._session.execute(
                    text(
                        """
                        UPDATE task_node_runs SET state='queued', version=version+1, updated_at=:now
                        WHERE task_node_run_id=:task_node_run_id AND state='dispatching'
                        """
                    ),
                    {"now": now, "task_node_run_id": row["task_node_run_id"]},
                )
                await self.release_concurrency_lock(str(row["task_node_run_id"]))
                continue
            await self._session.execute(
                text(
                    """
                    UPDATE agent_sessions SET status='dispatching', version=version+1, updated_at=:now
                    WHERE agent_session_id=:agent_session_id
                    """
                ),
                {"now": now, "agent_session_id": row["agent_session_id"]},
            )
            await self._session.execute(
                text(
                    """
                    UPDATE agent_instances SET status='dispatching', updated_at=:now
                    WHERE agent_instance_id=:agent_instance_id
                    """
                ),
                {"now": now, "agent_instance_id": row["agent_instance_id"]},
            )
            params_json = json.loads(row.pop("params_json") or "{}")
            row.pop("dependency_state_json", None)
            row["objective"] = str(params_json.get("objective", ""))
            row["fencing_token"] = f"{row['agent_run_id']}:{int(row['version']) + 1}"
            claimed.append(row)
        return claimed

    async def _try_acquire_concurrency_lock(
        self, row: Mapping[str, Any], now: datetime
    ) -> bool:
        group = row.get("concurrency_group")
        if not group:
            return True
        lock_key = f"{row['parent_task_id']}:{group}"
        result = await self._session.execute(
            text(
                """
                INSERT INTO task_concurrency_locks
                (lock_key, parent_task_id, concurrency_group, task_node_run_id, created_at, updated_at)
                VALUES (:lock_key, :parent_task_id, :concurrency_group, :task_node_run_id, :now, :now)
                ON CONFLICT(lock_key) DO NOTHING
                """
            ),
            {
                "lock_key": lock_key,
                "parent_task_id": row["parent_task_id"],
                "concurrency_group": group,
                "task_node_run_id": row["task_node_run_id"],
                "now": now,
            },
        )
        return result.rowcount == 1

    async def release_concurrency_lock(self, task_node_run_id: str) -> None:
        await self._session.execute(
            text("DELETE FROM task_concurrency_locks WHERE task_node_run_id=:task_node_run_id"),
            {"task_node_run_id": task_node_run_id},
        )

    async def routable_agent_run(
        self, agent_instance_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        """Return the owned live run that may execute one provider turn."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT ar.agent_run_id, ar.agent_session_id, ar.parent_task_id,
                           ar.task_node_run_id, ai.agent_instance_id, ai.agent_type,
                           ai.conversation_id
                    FROM agent_runs ar
                    JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                    WHERE ar.agent_instance_id=:agent_instance_id
                      AND ai.conversation_id=:conversation_id
                      AND ar.status='running'
                    ORDER BY ar.updated_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "agent_instance_id": agent_instance_id,
                    "conversation_id": conversation_id,
                },
            )
        ).mappings().first()
        return dict(row) if row else None

    async def create_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        agent_session_id: str,
        route_lock_id: str,
        canonical_model_id: str,
        routing_snapshot: Mapping[str, Any],
    ) -> None:
        now = utc_now()
        snapshot = json.dumps(routing_snapshot)
        await self._session.execute(
            text(
                """
                INSERT INTO agent_turns
                (turn_id, agent_run_id, agent_session_id, route_lock_id,
                 canonical_model_id, routing_snapshot_json, response_summary_json,
                 status, created_at)
                VALUES (:turn_id, :agent_run_id, :agent_session_id, :route_lock_id,
                        :canonical_model_id, :snapshot, '{}', 'running', :now)
                """
            ),
            {
                "turn_id": turn_id,
                "agent_run_id": agent_run_id,
                "agent_session_id": agent_session_id,
                "route_lock_id": route_lock_id,
                "canonical_model_id": canonical_model_id,
                "snapshot": snapshot,
                "now": now,
            },
        )
        await self._update_routing_snapshot(agent_run_id, snapshot, now)

    async def complete_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        routing_snapshot: Mapping[str, Any],
        response_summary: Mapping[str, Any],
    ) -> None:
        now = utc_now()
        snapshot = json.dumps(routing_snapshot)
        await self._session.execute(
            text(
                """
                UPDATE agent_turns
                SET status='completed', routing_snapshot_json=:snapshot,
                    response_summary_json=:summary, finished_at=:now
                WHERE turn_id=:turn_id AND status='running'
                """
            ),
            {
                "turn_id": turn_id,
                "snapshot": snapshot,
                "summary": json.dumps(response_summary),
                "now": now,
            },
        )
        await self._update_routing_snapshot(agent_run_id, snapshot, now)

    async def fail_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        routing_snapshot: Mapping[str, Any],
        error_class: str,
    ) -> None:
        now = utc_now()
        snapshot = json.dumps(routing_snapshot)
        await self._session.execute(
            text(
                """
                UPDATE agent_turns
                SET status='failed', routing_snapshot_json=:snapshot,
                    error_class=:error_class, finished_at=:now
                WHERE turn_id=:turn_id AND status='running'
                """
            ),
            {
                "turn_id": turn_id,
                "snapshot": snapshot,
                "error_class": error_class,
                "now": now,
            },
        )
        await self._update_routing_snapshot(agent_run_id, snapshot, now)

    async def _update_routing_snapshot(
        self, agent_run_id: str, snapshot: str, now: datetime
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE agent_runs
                SET routing_snapshot_json=:snapshot, version=version+1, updated_at=:now
                WHERE agent_run_id=:agent_run_id
                """
            ),
            {"agent_run_id": agent_run_id, "snapshot": snapshot, "now": now},
        )
        await self._session.execute(
            text(
                """
                UPDATE task_node_runs
                SET routing_snapshot_json=:snapshot, version=version+1, updated_at=:now
                WHERE task_node_run_id=(
                    SELECT task_node_run_id FROM agent_runs WHERE agent_run_id=:agent_run_id
                )
                """
            ),
            {"agent_run_id": agent_run_id, "snapshot": snapshot, "now": now},
        )

    async def list_routing_turns(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                """
                SELECT at.turn_id, at.agent_run_id, at.agent_session_id, at.route_lock_id,
                       at.canonical_model_id, at.routing_snapshot_json,
                       at.response_summary_json, at.status, at.error_class,
                       at.created_at, at.finished_at, ai.agent_instance_id, ai.agent_type,
                       rl.scope_type, rl.scope_id, rl.policy_version, rl.status AS lock_status
                FROM agent_turns at
                JOIN agent_runs ar ON ar.agent_run_id=at.agent_run_id
                JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                LEFT JOIN route_locks_v3 rl ON rl.id=at.route_lock_id
                WHERE ai.conversation_id=:conversation_id
                ORDER BY at.created_at DESC
                """
            ),
            {"conversation_id": conversation_id},
        )
        return [self._decode_audit_row(dict(row)) for row in rows.mappings().all()]

    async def routing_turn_detail(
        self, conversation_id: str, turn_id: str
    ) -> dict[str, Any] | None:
        rows = await self._session.execute(
            text(
                """
                SELECT at.turn_id, at.agent_run_id, at.agent_session_id, at.route_lock_id,
                       at.canonical_model_id, at.routing_snapshot_json,
                       at.response_summary_json, at.status, at.error_class,
                       at.created_at, at.finished_at, ai.agent_instance_id, ai.agent_type,
                       rl.scope_type, rl.scope_id, rl.policy_version, rl.status AS lock_status
                FROM agent_turns at
                JOIN agent_runs ar ON ar.agent_run_id=at.agent_run_id
                JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                LEFT JOIN route_locks_v3 rl ON rl.id=at.route_lock_id
                WHERE ai.conversation_id=:conversation_id AND at.turn_id=:turn_id
                """
            ),
            {"conversation_id": conversation_id, "turn_id": turn_id},
        )
        row = rows.mappings().first()
        if row is None:
            return None
        detail = self._decode_audit_row(dict(row))
        attempts = await self._session.execute(
            text(
                """
                SELECT id, route_lock_id, turn_id, attempt_index, provider_binding_id,
                       status, http_status, error_class, started_at, finished_at,
                       prompt_tokens, completion_tokens
                FROM route_attempts_v3
                WHERE turn_id=:turn_id
                ORDER BY attempt_index ASC, id ASC
                """
            ),
            {"turn_id": turn_id},
        )
        detail["attempts"] = [dict(row) for row in attempts.mappings().all()]
        return detail

    @staticmethod
    def _decode_audit_row(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("routing_snapshot_json", "response_summary_json"):
            raw = row.pop(key, "{}")
            row[key.removesuffix("_json")] = json.loads(raw) if raw else {}
        return row

    async def append_event(
        self,
        *,
        event_id: str,
        conversation_id: str,
        event_type: str,
        data: Mapping[str, Any],
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        """Persist an event after atomically advancing the conversation cursor."""
        await self._session.execute(
            text(
                """
                UPDATE conversations
                SET last_event_sequence=last_event_sequence+1, updated_at=:now
                WHERE conversation_id=:conversation_id
                """
            ),
            {"now": utc_now(), "conversation_id": conversation_id},
        )
        sequence = (
            await self._session.execute(
                text("SELECT last_event_sequence FROM conversations WHERE conversation_id=:conversation_id"),
                {"conversation_id": conversation_id},
            )
        ).scalar_one()
        await self._session.execute(
            text(
                """
                INSERT INTO conversation_events
                (event_id, conversation_id, agent_instance_id, agent_session_id, sequence,
                 event_type, data_json, idempotency_key, created_at)
                VALUES (:event_id, :conversation_id, :agent_instance_id, :agent_session_id,
                        :sequence, :event_type, :data_json, :idempotency_key, :created_at)
                """
            ),
            {
                "event_id": event_id,
                "conversation_id": conversation_id,
                "agent_instance_id": agent_instance_id,
                "agent_session_id": agent_session_id,
                "sequence": sequence,
                "event_type": event_type,
                "data_json": json.dumps(data),
                "idempotency_key": idempotency_key or event_id,
                "created_at": utc_now(),
            },
        )
        return int(sequence)

    async def conversation_events_after(
        self, conversation_id: str, after_sequence: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Return the authoritative conversation event replay window in order."""
        rows = await self._session.execute(
            text(
                """
                SELECT event_id, conversation_id, agent_instance_id, agent_session_id,
                       sequence, event_type, data_json, idempotency_key, created_at
                FROM conversation_events
                WHERE conversation_id=:conversation_id AND sequence > :after_sequence
                ORDER BY sequence ASC
                LIMIT :limit
                """
            ),
            {
                "conversation_id": conversation_id,
                "after_sequence": after_sequence,
                "limit": limit,
            },
        )
        events: list[dict[str, Any]] = []
        for raw in rows.mappings().all():
            row = dict(raw)
            row["data"] = json.loads(row.pop("data_json") or "{}")
            events.append(row)
        return events

    async def record_partial_stream_artifact(
        self,
        *,
        partial_artifact_id: str,
        conversation_id: str,
        agent_instance_id: str | None,
        agent_session_id: str | None,
        agent_run_id: str | None,
        stream_id: str,
        sequence: int,
        content_redacted: str,
        failure_reason: str,
    ) -> None:
        """Persist interrupted stream bytes outside the user-visible transcript."""
        await self._session.execute(
            text(
                """
                INSERT INTO partial_stream_artifacts
                (partial_artifact_id, conversation_id, agent_instance_id, agent_session_id,
                 agent_run_id, stream_id, sequence, content_redacted, failure_reason,
                 audit_only, created_at)
                VALUES (:partial_artifact_id, :conversation_id, :agent_instance_id,
                        :agent_session_id, :agent_run_id, :stream_id, :sequence,
                        :content_redacted, :failure_reason, 1, :created_at)
                """
            ),
            {
                "partial_artifact_id": partial_artifact_id,
                "conversation_id": conversation_id,
                "agent_instance_id": agent_instance_id,
                "agent_session_id": agent_session_id,
                "agent_run_id": agent_run_id,
                "stream_id": stream_id,
                "sequence": sequence,
                "content_redacted": content_redacted,
                "failure_reason": failure_reason[:512],
                "created_at": utc_now(),
            },
        )

    async def partial_stream_artifacts(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                """
                SELECT * FROM partial_stream_artifacts
                WHERE conversation_id=:conversation_id
                ORDER BY sequence ASC, created_at ASC
                """
            ),
            {"conversation_id": conversation_id},
        )
        artifacts: list[dict[str, Any]] = []
        for raw in rows.mappings().all():
            artifact = dict(raw)
            artifact["audit_only"] = bool(artifact["audit_only"])
            artifacts.append(artifact)
        return artifacts

    async def upsert_worktree(
        self,
        *,
        worktree_id: str,
        agent_instance_id: str,
        agent_run_id: str,
        path: str,
        branch: str,
        repo_root: str,
    ) -> None:
        """Persist the Git checkout allocated by the service for one coding agent."""
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO worktrees
                (worktree_id, agent_instance_id, agent_run_id, path, branch, repo_root,
                 status, created_at, updated_at)
                VALUES (:worktree_id, :agent_instance_id, :agent_run_id, :path, :branch,
                        :repo_root, 'active', :now, :now)
                ON CONFLICT(agent_instance_id) DO UPDATE SET
                    agent_run_id=excluded.agent_run_id,
                    path=excluded.path,
                    branch=excluded.branch,
                    repo_root=excluded.repo_root,
                    status='active',
                    quarantine_path=NULL,
                    cleanup_error=NULL,
                    removed_at=NULL,
                    updated_at=excluded.updated_at
                """
            ),
            {
                "worktree_id": worktree_id,
                "agent_instance_id": agent_instance_id,
                "agent_run_id": agent_run_id,
                "path": path,
                "branch": branch,
                "repo_root": repo_root,
                "now": now,
            },
        )

    async def active_worktree_for_agent(self, agent_instance_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT * FROM worktrees
                    WHERE agent_instance_id=:agent_instance_id
                      AND status IN ('active', 'cleanup_failed')
                    LIMIT 1
                    """
                ),
                {"agent_instance_id": agent_instance_id},
            )
        ).mappings().first()
        return dict(row) if row else None

    async def worktrees_for_reconciliation(self) -> list[dict[str, Any]]:
        """Read durable worktrees with the runtime state required at boot."""
        rows = await self._session.execute(
            text(
                """
                SELECT w.*, ai.status AS agent_instance_status,
                       EXISTS (
                           SELECT 1 FROM agent_runs ar
                           WHERE ar.agent_instance_id=w.agent_instance_id
                             AND ar.status IN ('dispatching', 'running')
                       ) AS runtime_active
                FROM worktrees w
                LEFT JOIN agent_instances ai ON ai.agent_instance_id=w.agent_instance_id
                WHERE w.status IN ('active', 'cleanup_failed')
                ORDER BY w.created_at ASC
                """
            )
        )
        return [dict(row) for row in rows.mappings().all()]

    async def record_worktree_cleanup(
        self,
        *,
        worktree_id: str,
        status: str,
        quarantine_path: str | None = None,
        cleanup_error: str | None = None,
    ) -> None:
        terminal = status in {"removed", "quarantined", "orphaned"}
        await self._session.execute(
            text(
                """
                UPDATE worktrees
                SET status=:status, quarantine_path=:quarantine_path,
                    cleanup_error=:cleanup_error,
                    removed_at=CASE WHEN :terminal THEN :now ELSE NULL END,
                    updated_at=:now
                WHERE worktree_id=:worktree_id
                """
            ),
            {
                "worktree_id": worktree_id,
                "status": status,
                "quarantine_path": quarantine_path,
                "cleanup_error": cleanup_error,
                "terminal": terminal,
                "now": utc_now(),
            },
        )

    async def conversation_id_for_parent_task(self, parent_task_id: str) -> str:
        """Return the owning conversation for one durable parent task."""
        result = await self._session.execute(
            text(
                """
                SELECT conversation_id FROM parent_tasks
                WHERE parent_task_id=:parent_task_id
                """
            ),
            {"parent_task_id": parent_task_id},
        )
        return str(result.scalar_one())

    async def conversation_id_for_agent(self, agent_instance_id: str) -> str:
        """Return the owning conversation for one durable agent instance."""
        result = await self._session.execute(
            text(
                """
                SELECT conversation_id FROM agent_instances
                WHERE agent_instance_id=:agent_instance_id
                """
            ),
            {"agent_instance_id": agent_instance_id},
        )
        return str(result.scalar_one())

    async def active_runs_for_agent(
        self, agent_instance_id: str, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        conversation_clause = ""
        params: dict[str, Any] = {"agent_instance_id": agent_instance_id}
        if conversation_id is not None:
            conversation_clause = """
                  AND EXISTS (
                    SELECT 1 FROM parent_tasks pt
                    WHERE pt.parent_task_id = ar.parent_task_id
                      AND pt.conversation_id = :conversation_id
                  )
            """
            params["conversation_id"] = conversation_id
        rows = await self._session.execute(
            text(
                """
                SELECT ar.*, tn.node_id
                FROM agent_runs ar
                JOIN task_node_runs tn ON tn.task_node_run_id=ar.task_node_run_id
                WHERE ar.agent_instance_id=:agent_instance_id
                  AND ar.status IN ('queued', 'dispatching', 'running')
                """
                + conversation_clause
                + """
                ORDER BY ar.created_at DESC
                """
            ),
            params,
        )
        return [dict(row) for row in rows.mappings().all()]

    async def has_agent_run_history(self, agent_instance_id: str) -> bool:
        """Return whether any real ``agent_runs`` row exists for the instance.

        This is the fail-closed guard for control-plane start/restart: an
        instance that ever had a real runtime run (even one that later
        completed, failed, or was cancelled) must not be marked RUNNING again
        without resurrecting that runtime.
        """
        result = await self._session.execute(
            text(
                """
                SELECT 1 FROM agent_runs
                WHERE agent_instance_id=:agent_instance_id
                LIMIT 1
                """
            ),
            {"agent_instance_id": agent_instance_id},
        )
        return result.first() is not None

    async def mark_agent_cancelled(
        self, agent_instance_id: str, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        runs = await self.active_runs_for_agent(agent_instance_id, conversation_id)
        if not runs:
            return []
        now = utc_now()
        for run in runs:
            await self._session.execute(
                text(
                    """
                    UPDATE agent_runs SET status='cancelled', version=version+1, updated_at=:now
                    WHERE agent_run_id=:agent_run_id AND status IN ('queued', 'dispatching', 'running')
                    """
                ),
                {"now": now, "agent_run_id": run["agent_run_id"]},
            )
            await self._session.execute(
                text(
                    """
                    UPDATE task_node_runs SET state='cancelled', version=version+1, updated_at=:now
                    WHERE task_node_run_id=:id
                      AND state IN ('queued', 'retry_wait', 'dispatching', 'running')
                    """
                ),
                {"now": now, "id": run["task_node_run_id"]},
            )
            await self.release_concurrency_lock(str(run["task_node_run_id"]))
            await self._session.execute(
                text("UPDATE agent_sessions SET status='cancelled', version=version+1, updated_at=:now WHERE agent_session_id=:id"),
                {"now": now, "id": run["agent_session_id"]},
            )
        await self._session.execute(
            text("UPDATE agent_instances SET status='cancelled', updated_at=:now WHERE agent_instance_id=:id"),
            {"now": now, "id": agent_instance_id},
        )
        return runs

    async def live_runs_with_owners(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                """
                SELECT ar.*, ai.agent_instance_id AS owner_agent_instance_id,
                       ai.agent_type AS owner_agent_type,
                       aps.agent_session_id AS owner_agent_session_id,
                       c.conversation_id
                FROM agent_runs ar
                LEFT JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                LEFT JOIN agent_sessions aps ON aps.agent_session_id=ar.agent_session_id
                LEFT JOIN parent_tasks pt ON pt.parent_task_id=ar.parent_task_id
                LEFT JOIN conversations c ON c.conversation_id=pt.conversation_id
                WHERE ar.status IN ('dispatching', 'running')
                ORDER BY ar.created_at ASC
                """
            )
        )
        return [dict(row) for row in rows.mappings().all()]

    async def mark_reattached(self, agent_run_id: str) -> None:
        await self._session.execute(
            text("UPDATE agent_runs SET status='running', updated_at=:now WHERE agent_run_id=:id"),
            {"now": utc_now(), "id": agent_run_id},
        )

    async def mark_orphaned(self, agent_run_id: str) -> None:
        await self._session.execute(
            text("UPDATE agent_runs SET status='cancelled', version=version+1, updated_at=:now WHERE agent_run_id=:id"),
            {"now": utc_now(), "id": agent_run_id},
        )

    async def running_agent_run(
        self, agent_instance_id: str, conversation_id: str, fencing_token: str | None = None
    ) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT ar.agent_run_id, ar.agent_session_id, ar.parent_task_id, ar.fencing_token,
                           ar.task_node_run_id, ar.status AS agent_run_status,
                           ai.agent_instance_id, ai.conversation_id,
                           tnr.state AS node_state, tnr.version AS node_version,
                           tnr.retry_state_json
                    FROM agent_runs ar
                    JOIN agent_instances ai ON ai.agent_instance_id=ar.agent_instance_id
                    JOIN task_node_runs tnr ON tnr.task_node_run_id=ar.task_node_run_id
                    WHERE ar.agent_instance_id=:agent_instance_id
                      AND ai.conversation_id=:conversation_id
                      AND ar.status='running' AND tnr.state='running'
                      AND (:fencing_token IS NULL OR ar.fencing_token=:fencing_token)
                    ORDER BY ar.updated_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "agent_instance_id": agent_instance_id,
                    "conversation_id": conversation_id,
                    "fencing_token": fencing_token,
                },
            )
        ).mappings().first()
        return dict(row) if row else None

    async def finalize_running_node(
        self,
        *,
        agent_run_id: str,
        task_node_run_id: str,
        parent_task_id: str,
        agent_instance_id: str,
        agent_session_id: str,
        expected_node_version: int,
        succeeded: bool,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        """Finish a node using CAS; cancellation wins over stale completion.

        Failed attempts move to ``retry_wait`` until the persisted cap is
        reached.  The next retry timestamp is calculated once and stored,
        making recovery deterministic even after a process restart.
        """
        now = utc_now()
        current = (
            await self._session.execute(
                text(
                    """
                    SELECT retry_state_json FROM task_node_runs
                    WHERE task_node_run_id=:task_node_run_id
                    """
                ),
                {"task_node_run_id": task_node_run_id},
            )
        ).mappings().first()
        if current is None:
            return None
        retry_state = json.loads(current["retry_state_json"] or "{}")
        terminal = succeeded
        target_state = "completed" if succeeded else "failed"
        next_retry_at: datetime | None = None
        if not succeeded:
            attempt = int(retry_state.get("attempt", 0)) + 1
            max_attempts = int(retry_state.get("max_attempts", 3))
            retry_state["attempt"] = attempt
            retry_state["max_attempts"] = max_attempts
            retry_state["last_error"] = error or "node failed"
            if attempt < max_attempts:
                digest = hashlib.sha256(
                    f"{task_node_run_id}:{attempt}".encode("utf-8")
                ).digest()
                jitter = int.from_bytes(digest[:2], "big") / 65535 * 0.25
                delay_seconds = min(60.0, float(2 ** (attempt - 1))) + jitter
                next_retry_at = now + timedelta(seconds=delay_seconds)
                retry_state["next_delay_seconds"] = delay_seconds
                target_state = "retry_wait"
                terminal = False

        facts_json = json.dumps(dict(result or {})) if succeeded else "{}"
        update_result = await self._session.execute(
            text(
                """
                UPDATE task_node_runs
                SET state=:target_state, facts_json=:facts_json,
                    retry_state_json=:retry_state_json, next_retry_at=:next_retry_at,
                    version=version+1, updated_at=:now
                WHERE task_node_run_id=:task_node_run_id
                  AND state='running' AND version=:expected_node_version
                """
            ),
            {
                "target_state": target_state,
                "facts_json": facts_json,
                "retry_state_json": json.dumps(retry_state),
                "next_retry_at": next_retry_at,
                "now": now,
                "task_node_run_id": task_node_run_id,
                "expected_node_version": expected_node_version,
            },
        )
        if update_result.rowcount != 1:
            return None

        run_status = "completed" if succeeded else ("queued" if not terminal else "failed")
        session_status = "completed" if succeeded else ("idle" if not terminal else "failed")
        instance_status = "completed" if succeeded else ("queued" if not terminal else "failed")
        await self._session.execute(
            text(
                """
                UPDATE agent_runs SET status=:status, version=version+1, updated_at=:now
                WHERE agent_run_id=:agent_run_id AND status='running'
                """
            ),
            {"status": run_status, "now": now, "agent_run_id": agent_run_id},
        )
        await self._session.execute(
            text(
                """
                UPDATE agent_sessions SET status=:status, version=version+1, updated_at=:now
                WHERE agent_session_id=:agent_session_id
                """
            ),
            {"status": session_status, "now": now, "agent_session_id": agent_session_id},
        )
        await self._session.execute(
            text("UPDATE agent_instances SET status=:status, updated_at=:now WHERE agent_instance_id=:agent_instance_id"),
            {"status": instance_status, "now": now, "agent_instance_id": agent_instance_id},
        )
        await self.release_concurrency_lock(task_node_run_id)

        if succeeded:
            incomplete = (
                await self._session.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM task_node_runs
                        WHERE parent_task_id=:parent_task_id AND state!='completed'
                        """
                    ),
                    {"parent_task_id": parent_task_id},
                )
            ).scalar_one()
            if int(incomplete) == 0:
                await self._session.execute(
                    text("UPDATE parent_tasks SET status='completed', updated_at=:now WHERE parent_task_id=:parent_task_id"),
                    {"now": now, "parent_task_id": parent_task_id},
                )
        return {
            "state": target_state,
            "terminal": terminal,
            "next_retry_at": next_retry_at,
            "node_version": expected_node_version + 1,
        }

    async def reserve_tool_execution(
        self,
        *,
        tool_execution_id: str,
        idempotency_key: str,
        agent_instance_id: str | None,
        tool_name: str,
        arguments_redacted: Mapping[str, Any],
        claimant: str,
    ) -> dict[str, Any]:
        """Reserve-and-claim a tool before its side effect can run."""
        now = utc_now()
        await self._session.execute(
            text(
                """
                INSERT INTO tool_executions
                (tool_execution_id, idempotency_key, agent_instance_id, tool_name,
                 arguments_redacted, status, claimant, created_at, updated_at)
                VALUES (:tool_execution_id, :idempotency_key, :agent_instance_id, :tool_name,
                        :arguments_redacted, 'reserved', NULL, :now, :now)
                ON CONFLICT(idempotency_key) DO NOTHING
                """
            ),
            {
                "tool_execution_id": tool_execution_id,
                "idempotency_key": idempotency_key,
                "agent_instance_id": agent_instance_id,
                "tool_name": tool_name,
                "arguments_redacted": json.dumps(arguments_redacted),
                "now": now,
            },
        )
        record = (
            await self._session.execute(
                text("SELECT * FROM tool_executions WHERE idempotency_key=:idempotency_key"),
                {"idempotency_key": idempotency_key},
            )
        ).mappings().one()
        claim = await self._session.execute(
            text(
                """
                UPDATE tool_executions
                SET status='running', claimant=:claimant, updated_at=:now
                WHERE tool_execution_id=:tool_execution_id
                  AND status='reserved' AND claimant IS NULL
                """
            ),
            {"claimant": claimant, "now": now, "tool_execution_id": record["tool_execution_id"]},
        )
        data = dict(record)
        data["claimed"] = claim.rowcount == 1
        if data["claimed"]:
            data["status"] = "running"
            data["claimant"] = claimant
        return data

    async def complete_tool_execution(
        self, *, tool_execution_id: str, claimant: str, result_ref: str | None
    ) -> bool:
        result = await self._session.execute(
            text(
                """
                UPDATE tool_executions
                SET status='completed', result_ref=:result_ref, updated_at=:now
                WHERE tool_execution_id=:tool_execution_id
                  AND status='running' AND claimant=:claimant
                """
            ),
            {
                "tool_execution_id": tool_execution_id,
                "claimant": claimant,
                "result_ref": result_ref,
                "now": utc_now(),
            },
        )
        return result.rowcount == 1

    async def list_agents(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                """
                SELECT ai.agent_instance_id, ai.parent_task_id, ai.agent_type, ai.status,
                       ai.permission_profile_json, ai.canonical_model_id, ai.assigned_node_id,
                       aps.agent_session_id, aps.windagent_session_id, aps.runtime_locator,
                       aps.hermes_run_id, aps.status AS session_status,
                       ar.agent_run_id, ar.status AS agent_run_status, ar.fencing_token,
                       tnr.task_node_run_id, tnr.state AS node_state, tnr.version AS node_version,
                       tnr.concurrency_group, tnr.next_retry_at,
                       wt.worktree_id, wt.path AS worktree_path, wt.branch AS worktree_branch,
                       wt.status AS worktree_status, wt.quarantine_path AS worktree_quarantine_path,
                       tn.tool_name AS planned_tool_name,
                       (
                           SELECT te.tool_name FROM tool_executions te
                           WHERE te.agent_instance_id=ai.agent_instance_id AND te.status='running'
                           ORDER BY te.updated_at DESC LIMIT 1
                       ) AS current_tool_name,
                       (
                           SELECT at.route_lock_id FROM agent_turns at
                           WHERE at.agent_run_id=ar.agent_run_id
                           ORDER BY at.created_at DESC LIMIT 1
                       ) AS route_lock_id,
                       (
                           SELECT ra.provider_binding_id FROM route_attempts_v3 ra
                           JOIN agent_turns at ON at.turn_id=ra.turn_id
                           WHERE at.agent_run_id=ar.agent_run_id
                           ORDER BY at.created_at DESC, ra.attempt_index DESC LIMIT 1
                       ) AS provider_binding_id
                FROM agent_instances ai
                LEFT JOIN agent_sessions aps ON aps.agent_instance_id=ai.agent_instance_id
                LEFT JOIN agent_runs ar ON ar.agent_instance_id=ai.agent_instance_id
                LEFT JOIN task_node_runs tnr ON tnr.task_node_run_id=ar.task_node_run_id
                LEFT JOIN worktrees wt ON wt.agent_instance_id=ai.agent_instance_id
                LEFT JOIN task_nodes tn ON tn.node_id=ai.assigned_node_id
                WHERE ai.conversation_id=:conversation_id
                ORDER BY ai.created_at ASC
                """
            ),
            {"conversation_id": conversation_id},
        )
        agents: list[dict[str, Any]] = []
        for raw in rows.mappings().all():
            agent = dict(raw)
            profile = agent.pop("permission_profile_json", None)
            agent["permission_profile"] = json.loads(profile) if profile else {}
            agents.append(agent)
        return agents

    async def list_task_graphs(self, conversation_id: str) -> list[dict[str, Any]]:
        """Read immutable plan snapshots and their durable node state for the UI."""
        plans_result = await self._session.execute(
            text(
                """
                SELECT pv.plan_version_id, pv.version, pv.dag_json,
                       pt.parent_task_id, pt.objective
                FROM task_plan_versions pv
                JOIN parent_tasks pt ON pt.parent_task_id=pv.parent_task_id
                WHERE pt.conversation_id=:conversation_id
                  AND pt.active_plan_version_id=pv.plan_version_id
                ORDER BY pv.created_at ASC
                """
            ),
            {"conversation_id": conversation_id},
        )
        graphs: list[dict[str, Any]] = []
        for plan_raw in plans_result.mappings().all():
            plan = dict(plan_raw)
            plan_id = str(plan["plan_version_id"])
            nodes_result = await self._session.execute(
                text(
                    """
                    SELECT tn.node_id, tn.position, tn.agent_type, tn.tool_name,
                           tn.params_json, tn.concurrency_group,
                           tnr.task_node_run_id, tnr.state AS status, tnr.version AS node_version,
                           tnr.next_retry_at, ai.agent_instance_id AS assigned_agent_instance_id
                    FROM task_nodes tn
                    LEFT JOIN task_node_runs tnr
                      ON tnr.plan_version_id=tn.plan_version_id AND tnr.node_id=tn.node_id
                    LEFT JOIN agent_instances ai
                      ON ai.assigned_node_id=tn.node_id AND ai.conversation_id=:conversation_id
                    WHERE tn.plan_version_id=:plan_version_id
                    ORDER BY tn.position ASC, tn.node_id ASC
                    """
                ),
                {"conversation_id": conversation_id, "plan_version_id": plan_id},
            )
            edges_result = await self._session.execute(
                text(
                    """
                    SELECT edge_id, from_node_id, to_node_id
                    FROM task_edges
                    WHERE plan_version_id=:plan_version_id
                    ORDER BY edge_id ASC
                    """
                ),
                {"plan_version_id": plan_id},
            )
            nodes: list[dict[str, Any]] = []
            for node_raw in nodes_result.mappings().all():
                node = dict(node_raw)
                params = json.loads(node.pop("params_json") or "{}")
                node["objective"] = str(params.get("objective") or "")
                nodes.append(node)
            graphs.append(
                {
                    "plan_version_id": plan_id,
                    "version": int(plan["version"]),
                    "parent_task_id": str(plan["parent_task_id"]),
                    "objective": str(plan["objective"]),
                    "nodes": nodes,
                    "edges": [dict(edge) for edge in edges_result.mappings().all()],
                }
            )
        return graphs

    # ─────────────────────────────────────────────────────────────────────
    # Control-plane seam (P4-R4B): idempotent conversation/agent CRUD and
    # lifecycle transitions for the V3 compatibility surface.
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _iso(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _decode_conversation(row: dict[str, Any]) -> dict[str, Any]:
        metadata = json.loads(row.pop("metadata_json") or "{}")
        row["id"] = row.pop("conversation_id")
        row["objective"] = metadata.get("objective", "")
        row["plan_version_id"] = metadata.get("plan_version_id")
        row["orchestrator_instance_id"] = metadata.get("orchestrator_instance_id")
        row["version"] = int(metadata.get("version", 1))
        row["created_at"] = MultiAgentRepository._iso(row.get("created_at"))
        row["updated_at"] = MultiAgentRepository._iso(row.get("updated_at"))
        return row

    @staticmethod
    def _decode_agent_instance(row: dict[str, Any]) -> dict[str, Any]:
        profile = json.loads(row.pop("permission_profile_json") or "{}")
        row["id"] = row.pop("agent_instance_id")
        row["definition_id"] = profile.get("definition_id") or "def-generalist-01"
        row["provider_binding_id"] = profile.get("provider_binding_id")
        row["route_lock_id"] = profile.get("route_lock_id")
        row["assigned_task_id"] = profile.get("assigned_task_id")
        row["current_tool"] = profile.get("current_tool")
        row["started_at"] = profile.get("started_at")
        row["stopped_at"] = profile.get("stopped_at")
        row["runtime_metadata"] = profile.get("runtime_metadata", {})
        row["version"] = int(row.pop("session_version") or 1)
        row["created_at"] = MultiAgentRepository._iso(row.get("created_at"))
        row["updated_at"] = MultiAgentRepository._iso(row.get("updated_at"))
        return row

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT conversation_id, title, status, metadata_json,
                           last_event_sequence, created_at, updated_at
                    FROM conversations
                    WHERE conversation_id=:conversation_id
                    """
                ),
                {"conversation_id": conversation_id},
            )
        ).mappings().first()
        return self._decode_conversation(dict(row)) if row is not None else None

    async def list_conversations(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                """
                SELECT conversation_id, title, status, metadata_json,
                       last_event_sequence, created_at, updated_at
                FROM conversations
                ORDER BY created_at ASC
                """
            )
        )
        return [self._decode_conversation(dict(row)) for row in rows.mappings().all()]

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        title: str | None,
        objective: str,
        plan_version_id: str | None = None,
        orchestrator_instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Idempotently persist a canonical conversation and return its projection."""
        existing = await self.get_conversation(conversation_id)
        if existing is not None:
            return existing
        now = utc_now()
        metadata = {
            "objective": objective,
            "plan_version_id": plan_version_id,
            "orchestrator_instance_id": orchestrator_instance_id,
            "version": 1,
        }
        await self._session.execute(
            text(
                """
                INSERT INTO conversations
                (conversation_id, title, status, metadata_json, last_event_sequence, created_at, updated_at)
                VALUES (:id, :title, 'active', :metadata, 0, :now, :now)
                """
            ),
            {
                "id": conversation_id,
                "title": title,
                "metadata": json.dumps(metadata),
                "now": now,
            },
        )
        return await self.get_conversation(conversation_id)

    async def get_agent_instance(self, agent_instance_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT ai.agent_instance_id, ai.conversation_id, ai.agent_type,
                           ai.status, ai.permission_profile_json, ai.canonical_model_id,
                           ai.created_at, ai.updated_at,
                           aps.agent_session_id, aps.status AS session_status,
                           aps.version AS session_version
                    FROM agent_instances ai
                    LEFT JOIN agent_sessions aps ON aps.agent_session_id = (
                        SELECT s.agent_session_id FROM agent_sessions s
                        WHERE s.agent_instance_id = ai.agent_instance_id
                        ORDER BY s.created_at ASC LIMIT 1
                    )
                    WHERE ai.agent_instance_id=:agent_instance_id
                    """
                ),
                {"agent_instance_id": agent_instance_id},
            )
        ).mappings().first()
        return self._decode_agent_instance(dict(row)) if row is not None else None

    async def list_agent_instances(
        self, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        clause = ""
        params: dict[str, Any] = {}
        if conversation_id is not None:
            clause = "WHERE ai.conversation_id=:conversation_id"
            params["conversation_id"] = conversation_id
        rows = await self._session.execute(
            text(
                """
                SELECT ai.agent_instance_id, ai.conversation_id, ai.agent_type,
                       ai.status, ai.permission_profile_json, ai.canonical_model_id,
                       ai.created_at, ai.updated_at,
                       aps.agent_session_id, aps.status AS session_status,
                       aps.version AS session_version
                FROM agent_instances ai
                LEFT JOIN agent_sessions aps ON aps.agent_session_id = (
                    SELECT s.agent_session_id FROM agent_sessions s
                    WHERE s.agent_instance_id = ai.agent_instance_id
                    ORDER BY s.created_at ASC LIMIT 1
                )
                """
                + clause
                + """
                ORDER BY ai.created_at ASC
                """
            ),
            params,
        )
        return [self._decode_agent_instance(dict(row)) for row in rows.mappings().all()]

    async def create_agent_instance(
        self,
        *,
        agent_instance_id: str,
        conversation_id: str,
        agent_session_id: str,
        agent_type: str,
        definition_id: str | None = None,
        canonical_model_id: str | None = None,
        runtime_metadata: Mapping[str, Any] | None = None,
        status: str = "active",
        started_at: str | None = None,
        stopped_at: str | None = None,
        provider_binding_id: str | None = None,
        route_lock_id: str | None = None,
        assigned_task_id: str | None = None,
        current_tool: str | None = None,
    ) -> dict[str, Any]:
        """Persist a control-plane agent instance plus its session atomically."""
        now = utc_now()
        profile = {
            "definition_id": definition_id,
            "runtime_metadata": dict(runtime_metadata or {}),
            "started_at": started_at,
            "stopped_at": stopped_at,
            "provider_binding_id": provider_binding_id,
            "route_lock_id": route_lock_id,
            "assigned_task_id": assigned_task_id,
            "current_tool": current_tool,
        }
        await self._session.execute(
            text(
                """
                INSERT INTO agent_instances
                (agent_instance_id, conversation_id, agent_type, status,
                 permission_profile_json, canonical_model_id, created_at, updated_at)
                VALUES (:id, :conversation_id, :agent_type, :status,
                        :profile, :canonical_model_id, :now, :now)
                """
            ),
            {
                "id": agent_instance_id,
                "conversation_id": conversation_id,
                "agent_type": agent_type,
                "status": status,
                "profile": json.dumps(profile),
                "canonical_model_id": canonical_model_id,
                "now": now,
            },
        )
        await self._session.execute(
            text(
                """
                INSERT INTO agent_sessions
                (agent_session_id, agent_instance_id, windagent_session_id, status,
                 version, created_at, updated_at)
                VALUES (:id, :agent_instance_id, :windagent_session_id, :status,
                        1, :now, :now)
                """
            ),
            {
                "id": agent_session_id,
                "agent_instance_id": agent_instance_id,
                "windagent_session_id": f"control:{agent_instance_id}",
                "status": status,
                "now": now,
            },
        )
        return await self.get_agent_instance(agent_instance_id)

    async def transition_agent_lifecycle(
        self,
        *,
        agent_instance_id: str,
        target_status: str,
        profile_updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """CAS lifecycle transition keyed on the durable ``agent_sessions.version``.

        The session version is the optimistic-concurrency source for agent
        lifecycle control.  ``profile_updates`` values are written verbatim
        (``None`` clears the compatibility key).
        """
        now = utc_now()
        current = (
            await self._session.execute(
                text(
                    """
                    SELECT aps.agent_session_id, aps.version, aps.status AS session_status,
                           ai.status AS instance_status, ai.conversation_id
                    FROM agent_instances ai
                    LEFT JOIN agent_sessions aps ON aps.agent_session_id = (
                        SELECT s.agent_session_id FROM agent_sessions s
                        WHERE s.agent_instance_id = ai.agent_instance_id
                        ORDER BY s.created_at ASC LIMIT 1
                    )
                    WHERE ai.agent_instance_id=:agent_instance_id
                    """
                ),
                {"agent_instance_id": agent_instance_id},
            )
        ).mappings().first()
        if current is None or current["agent_session_id"] is None:
            return None
        session_id = str(current["agent_session_id"])
        expected_version = int(current["version"])
        result = await self._session.execute(
            text(
                """
                UPDATE agent_sessions
                SET status=:status, version=version+1, updated_at=:now
                WHERE agent_session_id=:agent_session_id AND version=:expected_version
                """
            ),
            {
                "status": target_status,
                "now": now,
                "agent_session_id": session_id,
                "expected_version": expected_version,
            },
        )
        if result.rowcount != 1:
            return None
        profile_row = (
            await self._session.execute(
                text(
                    "SELECT permission_profile_json FROM agent_instances WHERE agent_instance_id=:id"
                ),
                {"id": agent_instance_id},
            )
        ).mappings().first()
        profile = (
            json.loads(profile_row["permission_profile_json"] or "{}")
            if profile_row is not None
            else {}
        )
        for key, value in (profile_updates or {}).items():
            profile[key] = value
        await self._session.execute(
            text(
                """
                UPDATE agent_instances
                SET status=:status, permission_profile_json=:profile, updated_at=:now
                WHERE agent_instance_id=:id
                """
            ),
            {
                "status": target_status,
                "profile": json.dumps(profile),
                "now": now,
                "id": agent_instance_id,
            },
        )
        return await self.get_agent_instance(agent_instance_id)

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT event_id, conversation_id, agent_instance_id, agent_session_id,
                           sequence, event_type, data_json, idempotency_key, created_at
                    FROM conversation_events
                    WHERE event_id=:event_id
                    """
                ),
                {"event_id": event_id},
            )
        ).mappings().first()
        if row is None:
            return None
        event = dict(row)
        event["data"] = json.loads(event.pop("data_json") or "{}")
        return event

    async def append_event_if_absent(
        self,
        *,
        event_id: str,
        conversation_id: str,
        event_type: str,
        data: Mapping[str, Any],
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> int | None:
        """Append an event only when its ``event_id`` is not already persisted."""
        existing = await self.get_event(event_id)
        if existing is not None:
            return None
        return await self.append_event(
            event_id=event_id,
            conversation_id=conversation_id,
            event_type=event_type,
            data=data,
            agent_instance_id=agent_instance_id,
            agent_session_id=agent_session_id,
        )
