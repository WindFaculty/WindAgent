"""Multi-agent repository port for WindAgent Core (Phase 3).

The orchestrator service and durable plan scheduler depend only on this port.
Concrete SQL implementation lives in storage (``MultiAgentRepository``).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


@runtime_checkable
class MultiAgentRepositoryPort(Protocol):
    """Persistence surface for Conversation/Agent/TaskNode aggregates.

    Methods only stage work on the supplied session; the caller owns the
    transaction boundary.
    """

    async def ensure_conversation(self, conversation_id: str, title: str | None = None) -> None: ...

    async def get_or_create_orchestrator(
        self, conversation_id: str, agent_instance_id: str, agent_session_id: str
    ) -> tuple[str, str, bool]: ...

    async def create_parent_task(
        self, parent_task_id: str, conversation_id: str, objective: str
    ) -> None: ...

    async def create_plan(
        self, plan_version_id: str, parent_task_id: str, dag: Mapping[str, Any]
    ) -> None: ...

    async def revision_context(
        self, *, conversation_id: str, parent_task_id: str
    ) -> dict[str, Any] | None: ...

    async def create_plan_revision(
        self,
        *,
        plan_version_id: str,
        parent_task_id: str,
        conversation_id: str,
        base_plan_version_id: str,
        version: int,
        dag: Mapping[str, Any],
    ) -> bool: ...

    async def list_plan_versions(
        self, *, conversation_id: str, parent_task_id: str
    ) -> list[dict[str, Any]]: ...

    async def create_nodes_and_edges(
        self,
        plan_version_id: str,
        nodes: Iterable[Mapping[str, Any]],
        edges: Iterable[Mapping[str, Any]],
    ) -> None: ...

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
    ) -> None: ...

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
    ) -> None: ...

    async def record_dispatch_failure(self, agent_run_id: str, reason: str) -> None: ...

    async def claim_ready_node_runs(
        self, parent_task_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def release_concurrency_lock(self, task_node_run_id: str) -> None: ...

    async def routable_agent_run(
        self, agent_instance_id: str, conversation_id: str
    ) -> dict[str, Any] | None: ...

    async def create_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        agent_session_id: str,
        route_lock_id: str,
        canonical_model_id: str,
        routing_snapshot: Mapping[str, Any],
    ) -> None: ...

    async def complete_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        routing_snapshot: Mapping[str, Any],
        response_summary: Mapping[str, Any],
    ) -> None: ...

    async def fail_agent_turn(
        self,
        *,
        turn_id: str,
        agent_run_id: str,
        routing_snapshot: Mapping[str, Any],
        error_class: str,
    ) -> None: ...

    async def list_routing_turns(self, conversation_id: str) -> list[dict[str, Any]]: ...

    async def routing_turn_detail(
        self, conversation_id: str, turn_id: str
    ) -> dict[str, Any] | None: ...

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
    ) -> int: ...

    async def conversation_events_after(
        self, conversation_id: str, after_sequence: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]: ...

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
    ) -> None: ...

    async def partial_stream_artifacts(self, conversation_id: str) -> list[dict[str, Any]]: ...

    async def upsert_worktree(
        self,
        *,
        worktree_id: str,
        agent_instance_id: str,
        agent_run_id: str,
        path: str,
        branch: str,
        repo_root: str,
    ) -> None: ...

    async def active_worktree_for_agent(self, agent_instance_id: str) -> dict[str, Any] | None: ...

    async def worktrees_for_reconciliation(self) -> list[dict[str, Any]]: ...

    async def record_worktree_cleanup(
        self,
        *,
        worktree_id: str,
        status: str,
        quarantine_path: str | None = None,
        cleanup_error: str | None = None,
    ) -> None: ...

    async def conversation_id_for_parent_task(self, parent_task_id: str) -> str: ...

    async def conversation_id_for_agent(self, agent_instance_id: str) -> str: ...

    async def active_runs_for_agent(
        self, agent_instance_id: str, conversation_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def has_agent_run_history(self, agent_instance_id: str) -> bool: ...

    async def mark_agent_cancelled(
        self, agent_instance_id: str, conversation_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def live_runs_with_owners(self) -> list[dict[str, Any]]: ...

    async def mark_reattached(self, agent_run_id: str) -> None: ...

    async def mark_orphaned(self, agent_run_id: str) -> None: ...

    async def running_agent_run(
        self,
        agent_instance_id: str,
        conversation_id: str,
        fencing_token: str | None = None,
    ) -> dict[str, Any] | None: ...

    async def complete_agent_run(
        self, agent_run_id: str, result_summary: Mapping[str, Any]
    ) -> None: ...

    async def fail_agent_run(
        self,
        agent_run_id: str,
        error_class: str,
        error_message: str,
        retry_after: float | None = None,
        max_attempts: int = 3,
    ) -> None: ...

    async def active_worktree_for_run(self, agent_run_id: str) -> dict[str, Any] | None: ...

    async def record_worktree_reattach(
        self, worktree_id: str, agent_run_id: str
    ) -> None: ...

    async def list_agents(self, conversation_id: str) -> list[dict[str, Any]]: ...

    async def list_task_graphs(self, conversation_id: str) -> list[dict[str, Any]]: ...

    # ─────────────────────────────────────────────────────────────────────
    # Control-plane seam (P4-R4B): idempotent conversation/agent CRUD and
    # lifecycle transitions for the V3 compatibility surface.  All methods
    # stage work on the supplied session; the caller owns the transaction.
    # ─────────────────────────────────────────────────────────────────────

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None: ...

    async def list_conversations(self) -> list[dict[str, Any]]: ...

    async def create_conversation(
        self,
        *,
        conversation_id: str,
        title: str | None,
        objective: str,
        plan_version_id: str | None = None,
        orchestrator_instance_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def get_agent_instance(self, agent_instance_id: str) -> dict[str, Any] | None: ...

    async def list_agent_instances(
        self, conversation_id: str | None = None
    ) -> list[dict[str, Any]]: ...

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
    ) -> dict[str, Any]: ...

    async def transition_agent_lifecycle(
        self,
        *,
        agent_instance_id: str,
        target_status: str,
        profile_updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...

    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    async def append_event_if_absent(
        self,
        *,
        event_id: str,
        conversation_id: str,
        event_type: str,
        data: Mapping[str, Any],
        agent_instance_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> int | None: ...


__all__ = ["MultiAgentRepositoryPort"]