# mypy: disable-error-code="return,unused-ignore"
"""Application service orchestrating Agent Runtime aggregates (Phase 13).

Every command runs inside one ``TransactionScope`` (platform UoW + outbox),
so the domain write and the durable event are atomically committed.  The
service validates aggregates through the pure domain layer and translates
rows to/from domain models at the boundary.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.time import Clock
from windagent.platform.observability import Telemetry

from ..domain.approvals import ApprovalState
from ..domain.budget import AgentBudgetLimits, AgentBudgetUsage, clamp_limits, inherit_limits
from ..domain.checkpoints import canonical_hash
from ..domain.delegation import DelegationStatus
from ..domain.errors import (
    AgentRuntimeNotFoundError,
    AgentRuntimeStaleVersionError,
    AgentRuntimeValidationError,
)
from ..domain.lifecycle import (
    AgentLoopLifecycle,
    AgentLoopState,
    SessionLifecycle,
    SessionState,
    StepLifecycle,
    StepState,
    TaskLifecycle,
    TaskState,
    WorkflowLifecycle,
    WorkflowState,
)
from ..domain.workflow import WorkflowDefinition, WorkflowEdge, WorkflowNode
from .events import AgentRuntimeEventFactory
from .models import (
    ApprovalRow,
    CheckpointRow,
    DelegationRow,
    RunRow,
    SessionRow,
    StepRow,
    TaskRow,
    WorkflowRow,
)
from .ports import TransactionScope


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _load(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AgentRuntimeService:
    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        clock: Clock,
        event_factory: AgentRuntimeEventFactory,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._clock = clock
        self._events = event_factory
        self._telemetry = telemetry

    # ------------------------------------------------------------------ #
    # Row -> View helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _session_view(row: SessionRow) -> Any:
        from .models import SessionView

        return SessionView(
            session_id=row.session_id,
            actor_id=row.actor_id,
            title=row.title,
            state=row.state,
            budget_limits=_load(row.budget_limits_json, {}),
            budget_usage=_load(row.budget_usage_json, {}),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _run_view(row: RunRow) -> Any:
        from .models import RunView

        return RunView(
            run_id=row.run_id,
            session_id=row.session_id,
            parent_run_id=row.parent_run_id,
            state=row.state,
            budget_scope=row.budget_scope,
            budget_limits=_load(row.budget_limits_json, {}),
            budget_usage=_load(row.budget_usage_json, {}),
            exhaustion_reason=row.exhaustion_reason,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            timeout_seconds=row.timeout_seconds,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            completed_at=_as_utc(row.completed_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _task_view(row: TaskRow) -> Any:
        from .models import TaskView

        return TaskView(
            task_id=row.task_id,
            session_id=row.session_id,
            run_id=row.run_id,
            workflow_id=row.workflow_id,
            title=row.title,
            description=row.description,
            state=row.state,
            priority=row.priority,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            timeout_seconds=row.timeout_seconds,
            input_payload=_load(row.input_payload_json, {}),
            output_payload=_load(row.output_payload_json, None) if row.output_payload_json else None,
            error=row.error,
            awaiting_approval_id=row.awaiting_approval_id,
            checkpoint_id=row.checkpoint_id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            completed_at=_as_utc(row.completed_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _workflow_view(row: WorkflowRow) -> Any:
        from .models import WorkflowView

        return WorkflowView(
            workflow_id=row.workflow_id,
            session_id=row.session_id,
            name=row.name,
            version=row.version,
            state=row.state,
            nodes=_load(row.nodes_json, {}),
            edges=_load(row.edges_json, []),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
            metadata=_load(row.metadata_json, {}),
        )

    @staticmethod
    def _step_view(row: StepRow) -> Any:
        from .models import StepView

        return StepView(
            step_id=row.step_id,
            workflow_id=row.workflow_id,
            run_id=row.run_id,
            task_id=row.task_id,
            node_id=row.node_id,
            state=row.state,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            priority=row.priority,
            result=_load(row.result_json, None) if row.result_json else None,
            error=row.error,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            optimistic_version=row.optimistic_version,
        )

    @staticmethod
    def _checkpoint_view(row: CheckpointRow) -> Any:
        from .models import CheckpointView

        return CheckpointView(
            checkpoint_id=row.checkpoint_id,
            run_id=row.run_id,
            task_id=row.task_id,
            workflow_id=row.workflow_id,
            step_id=row.step_id,
            seq=row.seq,
            state_snapshot=_load(row.state_snapshot_json, {}),
            snapshot_hash=row.snapshot_hash,
            created_at=_as_utc(row.created_at),
        )

    @staticmethod
    def _approval_view(row: ApprovalRow) -> Any:
        from .models import ApprovalView

        return ApprovalView(
            approval_id=row.approval_id,
            task_id=row.task_id,
            run_id=row.run_id,
            requested_by=row.requested_by,
            state=row.state,
            payload=_load(row.payload_json, {}),
            resolution=_load(row.resolution_json, None) if row.resolution_json else None,
            created_at=_as_utc(row.created_at),
            resolved_at=_as_utc(row.resolved_at),
            expires_at=_as_utc(row.expires_at),
        )

    @staticmethod
    def _delegation_view(row: DelegationRow) -> Any:
        from .models import DelegationView

        return DelegationView(
            delegation_id=row.delegation_id,
            parent_run_id=row.parent_run_id,
            child_run_id=row.child_run_id,
            status=row.status,
            created_at=_as_utc(row.created_at),
            completed_at=_as_utc(row.completed_at),
            metadata=_load(row.metadata_json, {}),
        )

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #

    async def create_session(
        self, *, actor_id: str = "system", title: str = "Untitled session", budget_limits: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None
    ) -> Any:
        normalized_title = title.strip() if title.strip() else "Untitled session"
        if not actor_id.strip():
            raise AgentRuntimeValidationError("actor_id cannot be blank.")
        # Validate budget limits schema
        limits = clamp_limits(budget_limits or {})
        session_id = _new_id()
        now = datetime.now(UTC)
        row = SessionRow(
            session_id=session_id,
            actor_id=actor_id.strip(),
            title=normalized_title,
            state=SessionState.IDLE.value,
            budget_limits_json=_dump(limits.model_dump(exclude_none=True)),
            budget_usage_json=_dump(AgentBudgetUsage().model_dump()),
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            ok = await store.insert_session(row)
            if not ok:
                raise AgentRuntimeValidationError("Session id collision — retry.", context={"session_id": session_id})
            await scope.record_event(self._events.session_created(session_id, actor_id.strip()))
            await scope.commit()
            inserted = await store.get_session(session_id)
            assert inserted is not None
            return self._session_view(inserted)

    async def transition_session(self, *, session_id: str, target_state: str, expected_version: int | None = None) -> Any:
        try:
            target = SessionState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown session state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_session(session_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Session {session_id!r} not found.", context={"session_id": session_id})
            current = SessionState(existing.state)
            # stale check
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Session optimistic version mismatch.", context={"session_id": session_id})
            SessionLifecycle.transition(current, target)
            if current == target:
                return self._session_view(existing)
            updated = await store.update_session(
                session_id,
                state=target.value,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Session optimistic version mismatch.", context={"session_id": session_id})
            await scope.record_event(self._events.session_transitioned(session_id, current.value, target.value))
            await scope.commit()
            return self._session_view(updated)

    async def get_session(self, session_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_session(session_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Session {session_id!r} not found.", context={"session_id": session_id})
            return self._session_view(row)

    async def list_sessions(self, actor_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_sessions(actor_id)
            return tuple(self._session_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #

    async def create_run(
        self,
        *,
        session_id: str,
        parent_run_id: str | None = None,
        budget_scope: str = "conversation",
        budget_limits: dict[str, Any] | None = None,
        max_attempts: int = 3,
        timeout_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if not session_id.strip():
            raise AgentRuntimeValidationError("session_id cannot be blank.")
        if max_attempts < 1:
            raise AgentRuntimeValidationError("max_attempts must be >= 1.")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise AgentRuntimeValidationError("timeout_seconds must be > 0.")
        # Validate scope
        from ..domain.budget import BudgetScope

        try:
            scope_enum = BudgetScope(budget_scope)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown budget scope {budget_scope!r}.") from exc
        limits = clamp_limits(budget_limits or {})
        # If parent, inherit limits (component-wise minimum)
        async with self._scope_factory() as scope:
            store = scope.store()
            session = await store.get_session(session_id)
            if session is None:
                raise AgentRuntimeNotFoundError(f"Session {session_id!r} not found.", context={"session_id": session_id})
            parent_limits = None
            if parent_run_id is not None:
                parent = await store.get_run(parent_run_id)
                if parent is None:
                    raise AgentRuntimeNotFoundError(f"Parent run {parent_run_id!r} not found.", context={"run_id": parent_run_id})
                if parent.session_id != session_id:
                    raise AgentRuntimeValidationError("Parent run session mismatch.")
                # inherit
                parent_limits = AgentBudgetLimits(**_load(parent.budget_limits_json, {}))
                limits = inherit_limits(parent_limits, limits)
                # Recursion depth check: count delegation chain depth by walking parents (bounded by retrieval)
                # For now increment child_agents count in parent usage lazily via update; we keep simple.
            run_id = _new_id()
            now = datetime.now(UTC)
            row = RunRow(
                run_id=run_id,
                session_id=session_id,
                parent_run_id=parent_run_id,
                state=AgentLoopState.CREATED.value,
                budget_scope=scope_enum.value,
                budget_limits_json=_dump(limits.model_dump(exclude_none=True)),
                budget_usage_json=_dump(AgentBudgetUsage().model_dump()),
                exhaustion_reason=None,
                attempt=1,
                max_attempts=max_attempts,
                timeout_seconds=timeout_seconds,
                created_at=now,
                updated_at=now,
                completed_at=None,
                optimistic_version=0,
                metadata_json=_dump(metadata or {}),
            )
            ok = await store.insert_run(row)
            if not ok:
                raise AgentRuntimeValidationError("Run id collision — retry.")
            await scope.record_event(self._events.run_created(run_id, session_id))
            # If delegated, also create delegation row? Caller will call delegate separately.
            await scope.commit()
            inserted = await store.get_run(run_id)
            assert inserted is not None
            return self._run_view(inserted)

    async def transition_run(
        self, *, run_id: str, target_state: str, expected_version: int | None = None, exhaustion_reason: str | None = None
    ) -> Any:
        try:
            target = AgentLoopState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown run state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_run(run_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            current = AgentLoopState(existing.state)
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Run optimistic version mismatch.", context={"run_id": run_id})
            AgentLoopLifecycle.transition(current, target)
            if current == target:
                return self._run_view(existing)
            # Budget exhaustion auto-fails if set
            completed_at: datetime | None
            if target in (AgentLoopState.FAILED, AgentLoopState.CANCELLED, AgentLoopState.COMPLETED, AgentLoopState.ORPHANED):
                completed_at = datetime.now(UTC)
            else:
                completed_at = existing.completed_at
            updated = await store.update_run(
                run_id,
                state=target.value,
                exhaustion_reason=exhaustion_reason,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                completed_at=completed_at,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Run optimistic version mismatch.", context={"run_id": run_id})
            await scope.record_event(self._events.run_transitioned(run_id, current.value, target.value))
            if exhaustion_reason is not None:
                await scope.record_event(self._events.run_budget_exhausted(run_id, exhaustion_reason))
            await scope.commit()
            return self._run_view(updated)

    async def record_run_budget_usage(self, *, run_id: str, usage_patch: dict[str, Any], expected_version: int | None = None) -> Any:
        if not usage_patch:
            return await self.get_run(run_id)
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_run(run_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Run optimistic version mismatch.", context={"run_id": run_id})
            current_usage = AgentBudgetUsage(**_load(existing.budget_usage_json, {}))
            # Apply patch as increments (positive deltas)
            patch = {}
            for k, v in usage_patch.items():
                if k in AgentBudgetUsage.model_fields:
                    patch[k] = v
            # Build new usage by adding deltas for numeric fields
            new_usage_dict = current_usage.model_dump()
            for k, delta in patch.items():
                if k in ("cost_usd",):
                    new_usage_dict[k] = float(new_usage_dict.get(k, 0) or 0) + float(delta)
                else:
                    new_usage_dict[k] = int(new_usage_dict.get(k, 0) or 0) + int(delta)
            new_usage = AgentBudgetUsage(**new_usage_dict)
            limits = AgentBudgetLimits(**_load(existing.budget_limits_json, {}))
            # Check exhaustion
            snapshot_reason = None
            # inline exhaustion check
            if limits.max_turns is not None and new_usage.turns >= limits.max_turns:
                snapshot_reason = "max_turns"
            elif limits.max_tokens is not None and new_usage.tokens >= limits.max_tokens:
                snapshot_reason = "max_tokens"
            elif limits.max_cost_usd is not None and new_usage.cost_usd >= limits.max_cost_usd:
                snapshot_reason = "max_cost_usd"
            elif limits.max_wall_time_seconds is not None and new_usage.wall_time_seconds >= limits.max_wall_time_seconds:
                snapshot_reason = "max_wall_time_seconds"
            elif limits.max_model_failures is not None and new_usage.model_failures >= limits.max_model_failures:
                snapshot_reason = "max_model_failures"
            elif limits.max_tool_failures is not None and new_usage.tool_failures >= limits.max_tool_failures:
                snapshot_reason = "max_tool_failures"
            elif limits.max_retries is not None and new_usage.retries >= limits.max_retries:
                snapshot_reason = "max_retries"
            elif limits.max_child_agents is not None and new_usage.child_agents >= limits.max_child_agents:
                snapshot_reason = "max_child_agents"
            elif limits.max_recursion_depth is not None and new_usage.recursion_depth >= limits.max_recursion_depth:
                snapshot_reason = "max_recursion_depth"
            updated = await store.update_run(
                run_id,
                budget_usage_json=_dump(new_usage.model_dump()),
                exhaustion_reason=snapshot_reason,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Run optimistic version mismatch.", context={"run_id": run_id})
            if snapshot_reason is not None and updated.state != AgentLoopState.FAILED.value:
                # Auto-transition to FAILED on exhaustion (fail-closed)
                try:
                    await store.update_run(
                        run_id,
                        state=AgentLoopState.FAILED.value,
                        exhaustion_reason=snapshot_reason,
                        optimistic_version=updated.optimistic_version + 1,
                        expected_version=updated.optimistic_version,
                    )
                    after = await store.get_run(run_id)
                    if after is not None:
                        updated = after
                    await scope.record_event(self._events.run_budget_exhausted(run_id, snapshot_reason))
                    await scope.record_event(self._events.run_transitioned(run_id, existing.state, AgentLoopState.FAILED.value))
                except Exception:
                    pass
            await scope.commit()
            refreshed = await store.get_run(run_id)
            assert refreshed is not None
            return self._run_view(refreshed)

    async def get_run(self, run_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_run(run_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            return self._run_view(row)

    async def list_runs(self, session_id: str | None = None, parent_run_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_runs(session_id, parent_run_id)
            return tuple(self._run_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    async def create_task(
        self,
        *,
        session_id: str,
        title: str,
        description: str = "",
        run_id: str | None = None,
        workflow_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        timeout_seconds: float | None = None,
        input_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        normalized = title.strip()
        if not normalized:
            raise AgentRuntimeValidationError("Task title cannot be blank.")
        if max_attempts < 1:
            raise AgentRuntimeValidationError("max_attempts must be >= 1.")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise AgentRuntimeValidationError("timeout_seconds must be > 0.")
        task_id = _new_id()
        now = datetime.now(UTC)
        row = TaskRow(
            task_id=task_id,
            session_id=session_id,
            run_id=run_id,
            workflow_id=workflow_id,
            title=normalized,
            description=description,
            state=TaskState.RECEIVED.value,
            priority=priority,
            attempt=1,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            input_payload_json=_dump(input_payload or {}),
            output_payload_json=None,
            error=None,
            awaiting_approval_id=None,
            checkpoint_id=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            session = await store.get_session(session_id)
            if session is None:
                raise AgentRuntimeNotFoundError(f"Session {session_id!r} not found.", context={"session_id": session_id})
            if run_id is not None:
                run = await store.get_run(run_id)
                if run is None:
                    raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            if workflow_id is not None:
                wf = await store.get_workflow(workflow_id)
                if wf is None:
                    raise AgentRuntimeNotFoundError(f"Workflow {workflow_id!r} not found.", context={"workflow_id": workflow_id})
            ok = await store.insert_task(row)
            if not ok:
                raise AgentRuntimeValidationError("Task id collision — retry.")
            await scope.record_event(self._events.task_created(task_id, session_id))
            await scope.commit()
            inserted = await store.get_task(task_id)
            assert inserted is not None
            return self._task_view(inserted)

    async def transition_task(self, *, task_id: str, target_state: str, expected_version: int | None = None) -> Any:
        try:
            target = TaskState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown task state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_task(task_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            current = TaskState(existing.state)
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            TaskLifecycle.transition(current, target)
            if current == target:
                return self._task_view(existing)
            completed_at: datetime | None = None
            if target in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                completed_at = datetime.now(UTC)
            updated = await store.update_task(
                task_id,
                state=target.value,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                completed_at=completed_at,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
            if target == TaskState.COMPLETED:
                await scope.record_event(self._events.task_completed(task_id))
            elif target == TaskState.FAILED:
                await scope.record_event(self._events.task_failed(task_id, updated.error or ""))
            await scope.commit()
            return self._task_view(updated)

    async def complete_task(self, *, task_id: str, output_payload: dict[str, Any] | None = None, expected_version: int | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_task(task_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            current = TaskState(existing.state)
            # Allow completing from RUNNING, VERIFYING, REVIEWING directly; enforce transition
            target = TaskState.COMPLETED
            TaskLifecycle.transition(current, target)
            completed_at = datetime.now(UTC)
            updated = await store.update_task(
                task_id,
                state=target.value,
                output_payload_json=_dump(output_payload or {}),
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                completed_at=completed_at,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
            await scope.record_event(self._events.task_completed(task_id))
            await scope.commit()
            return self._task_view(updated)

    async def fail_task(self, *, task_id: str, error: str = "", expected_version: int | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_task(task_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            current = TaskState(existing.state)
            target = TaskState.FAILED
            # If already terminal, keep idempotent
            if current in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                raise AgentRuntimeValidationError(f"Task is already terminal {current.value}.")
            # Validate transition via lifecycle (will raise if illegal)
            TaskLifecycle.transition(current, target)
            completed_at = datetime.now(UTC)
            updated = await store.update_task(
                task_id,
                state=target.value,
                error=error or "task failed",
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                completed_at=completed_at,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
            await scope.record_event(self._events.task_failed(task_id, error))
            await scope.commit()
            return self._task_view(updated)

    async def retry_task(self, *, task_id: str, expected_version: int | None = None) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_task(task_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
            if existing.attempt >= existing.max_attempts:
                raise AgentRuntimeValidationError(f"Task max_attempts ({existing.max_attempts}) exhausted.", context={"task_id": task_id})
            # Determine retry path: FAILED -> RETRY_WAIT -> RUNNING etc.  We model retry as FAIL->RETRY_WAIT if not already
            current = TaskState(existing.state)
            # Allow retry from FAILED or RETRY_WAIT or RECOVERING
            if current == TaskState.FAILED:
                # FAILED -> RETRY_WAIT -> RUNNING (two hops, single attempt bump)
                target = TaskState.RETRY_WAIT
                TaskLifecycle.transition(current, target)
                mid = await store.update_task(
                    task_id,
                    state=target.value,
                    attempt=existing.attempt + 1,
                    error=None,
                    optimistic_version=existing.optimistic_version + 1,
                    expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                )
                if mid is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
                after = await store.get_task(task_id)
                assert after is not None
                TaskLifecycle.transition(TaskState(after.state), TaskState.RUNNING)
                updated = await store.update_task(
                    task_id,
                    state=TaskState.RUNNING.value,
                    optimistic_version=after.optimistic_version + 1,
                    expected_version=after.optimistic_version,
                )
                if updated is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, target.value, TaskState.RUNNING.value))
                await scope.commit()
                return self._task_view(updated)
            elif current in (TaskState.RETRY_WAIT, TaskState.RECOVERING):
                # Direct RETRY_WAIT/RECOVERING -> RUNNING with attempt bump
                target = TaskState.RUNNING
                TaskLifecycle.transition(current, target)
                updated = await store.update_task(
                    task_id,
                    state=target.value,
                    attempt=existing.attempt + 1,
                    error=None,
                    optimistic_version=existing.optimistic_version + 1,
                    expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                )
                if updated is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
                await scope.commit()
                return self._task_view(updated)
            else:
                # For other states, we set to RETRY_WAIT first then RUNNING
                target = TaskState.RETRY_WAIT
                TaskLifecycle.transition(current, target)
                mid = await store.update_task(
                    task_id,
                    state=target.value,
                    attempt=existing.attempt + 1,
                    error=None,
                    optimistic_version=existing.optimistic_version + 1,
                    expected_version=expected_version if expected_version is not None else existing.optimistic_version,
                )
                if mid is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, current.value, target.value))
                # Now move to RUNNING
                after = await store.get_task(task_id)
                assert after is not None
                # Validate RETRY_WAIT -> RUNNING
                TaskLifecycle.transition(TaskState(after.state), TaskState.RUNNING)
                updated = await store.update_task(
                    task_id,
                    state=TaskState.RUNNING.value,
                    optimistic_version=after.optimistic_version + 1,
                    expected_version=after.optimistic_version,
                )
                if updated is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, target.value, TaskState.RUNNING.value))
                await scope.commit()
                return self._task_view(updated)

    async def get_task(self, task_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_task(task_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            return self._task_view(row)

    async def list_tasks(
        self, session_id: str | None = None, run_id: str | None = None, workflow_id: str | None = None, state: str | None = None
    ) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_tasks(session_id, run_id, workflow_id, state)
            return tuple(self._task_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Workflows
    # ------------------------------------------------------------------ #

    async def create_workflow(
        self, *, session_id: str, name: str, nodes: dict[str, Any] | None = None, edges: list[dict[str, Any]] | None = None, metadata: dict[str, Any] | None = None
    ) -> Any:
        normalized = name.strip()
        if not normalized:
            raise AgentRuntimeValidationError("Workflow name cannot be blank.")
        # Validate session exists
        async with self._scope_factory() as scope:
            store = scope.store()
            session = await store.get_session(session_id)
            if session is None:
                raise AgentRuntimeNotFoundError(f"Session {session_id!r} not found.", context={"session_id": session_id})
        # Build domain DAG for validation
        nodes_dict: dict[str, WorkflowNode] = {}
        for node_id, raw in (nodes or {}).items():
            if isinstance(raw, dict):
                # raw may already contain id; ensure it matches key
                nid = str(raw.get("id") or node_id)
                nodes_dict[nid] = WorkflowNode(
                    id=nid,
                    name=str(raw.get("name") or nid),
                    tool_name=str(raw.get("tool_name") or ""),
                    params=dict(raw.get("params") or {}),
                    priority=int(raw.get("priority") or 0),
                    timeout_seconds=raw.get("timeout_seconds"),
                    max_attempts=int(raw.get("max_attempts") or 3),
                )
            else:
                raise AgentRuntimeValidationError(f"Invalid node payload for {node_id!r}.")
        edges_list: list[WorkflowEdge] = []
        for raw in (edges or []):
            if isinstance(raw, dict):
                edges_list.append(WorkflowEdge(from_node_id=str(raw["from_node_id"]), to_node_id=str(raw["to_node_id"]), condition=raw.get("condition"), edge_type=str(raw.get("edge_type") or "dependency")))
            else:
                raise AgentRuntimeValidationError("Invalid edge payload.")
        # If nodes provided inline, allow empty but validate if non-empty
        wf_def = WorkflowDefinition(id="tmp", name=normalized, nodes=nodes_dict, edges=edges_list)
        if nodes_dict:
            wf_def.validate_dag()
        workflow_id = _new_id()
        # Persist nodes/edges as JSON
        now = datetime.now(UTC)
        row = WorkflowRow(
            workflow_id=workflow_id,
            session_id=session_id,
            name=normalized,
            version=1,
            state=WorkflowState.DRAFT.value,
            nodes_json=_dump({nid: n.model_dump() for nid, n in nodes_dict.items()}),
            edges_json=_dump([e.model_dump() for e in edges_list]),
            created_at=now,
            updated_at=now,
            optimistic_version=0,
            metadata_json=_dump(metadata or {}),
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            ok = await store.insert_workflow(row)
            if not ok:
                raise AgentRuntimeValidationError("Workflow id collision — retry.")
            await scope.record_event(self._events.workflow_created(workflow_id, session_id))
            await scope.commit()
            inserted = await store.get_workflow(workflow_id)
            assert inserted is not None
            return self._workflow_view(inserted)

    async def transition_workflow(self, *, workflow_id: str, target_state: str, expected_version: int | None = None) -> Any:
        try:
            target = WorkflowState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown workflow state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_workflow(workflow_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Workflow {workflow_id!r} not found.", context={"workflow_id": workflow_id})
            current = WorkflowState(existing.state)
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Workflow optimistic version mismatch.", context={"workflow_id": workflow_id})
            WorkflowLifecycle.transition(current, target)
            if current == target:
                return self._workflow_view(existing)
            # If transitioning to RUNNING, validate DAG not empty
            if target == WorkflowState.RUNNING:
                nodes = _load(existing.nodes_json, {})
                if not nodes:
                    raise AgentRuntimeValidationError("Cannot run workflow with no nodes.")
            updated = await store.update_workflow(
                workflow_id,
                state=target.value,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Workflow optimistic version mismatch.", context={"workflow_id": workflow_id})
            await scope.record_event(self._events.workflow_transitioned(workflow_id, current.value, target.value))
            await scope.commit()
            return self._workflow_view(updated)

    async def schedule_workflow(self, *, workflow_id: str, run_id: str, expected_version: int | None = None) -> Any:
        """Transition workflow to RUNNING and materialize steps for each node."""
        async with self._scope_factory() as scope:
            store = scope.store()
            wf = await store.get_workflow(workflow_id)
            if wf is None:
                raise AgentRuntimeNotFoundError(f"Workflow {workflow_id!r} not found.", context={"workflow_id": workflow_id})
            run = await store.get_run(run_id)
            if run is None:
                raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            if wf.session_id != run.session_id:
                raise AgentRuntimeValidationError("Workflow and run must share session.")
            current = WorkflowState(wf.state)
            if current not in (WorkflowState.DRAFT, WorkflowState.READY, WorkflowState.PENDING):
                raise AgentRuntimeValidationError(f"Workflow state {current.value} cannot be scheduled.")
            if expected_version is not None and wf.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Workflow optimistic version mismatch.", context={"workflow_id": workflow_id})
            # Validate DAG
            nodes_dict = {nid: WorkflowNode(**raw) for nid, raw in _load(wf.nodes_json, {}).items()}
            edges_list = [WorkflowEdge(**raw) for raw in _load(wf.edges_json, [])]
            wf_def = WorkflowDefinition(id=workflow_id, name=wf.name, nodes=nodes_dict, edges=edges_list)
            if nodes_dict:
                wf_def.validate_dag()
            # Transition to RUNNING if needed
            target = WorkflowState.RUNNING
            # Allow DRAFT->RUNNING? According to lifecycle DRAFT only to READY, but for ergonomics we allow DRAFT->READY->RUNNING in one call
            # So first ensure READY if DRAFT
            intermediate = wf
            if current == WorkflowState.DRAFT:
                # DRAFT -> READY
                WorkflowLifecycle.transition(current, WorkflowState.READY)
                mid = await store.update_workflow(
                    workflow_id,
                    state=WorkflowState.READY.value,
                    optimistic_version=intermediate.optimistic_version + 1,
                    expected_version=intermediate.optimistic_version,
                )
                assert mid is not None
                await scope.record_event(self._events.workflow_transitioned(workflow_id, current.value, WorkflowState.READY.value))
                intermediate = mid
                current = WorkflowState.READY
            # Now READY -> RUNNING (or PENDING -> RUNNING)
            WorkflowLifecycle.transition(current, target)
            updated = await store.update_workflow(
                workflow_id,
                state=target.value,
                optimistic_version=intermediate.optimistic_version + 1,
                expected_version=intermediate.optimistic_version,
            )
            assert updated is not None
            await scope.record_event(self._events.workflow_transitioned(workflow_id, current.value, target.value))
            # Materialize steps
            # Determine initial states: nodes with no incoming edges start as PENDING (then scheduler will move to READY)
            preds: dict[str, set[str]] = {nid: set() for nid in nodes_dict}
            for e in edges_list:
                preds[e.to_node_id].add(e.from_node_id)
            now = datetime.now(UTC)
            for nid, node in nodes_dict.items():
                step_id = _new_id()
                initial_state = StepState.PENDING if not preds[nid] else StepState.BLOCKED
                step_row = StepRow(
                    step_id=step_id,
                    workflow_id=workflow_id,
                    run_id=run_id,
                    task_id=None,
                    node_id=nid,
                    state=initial_state.value,
                    attempt=1,
                    max_attempts=node.max_attempts,
                    priority=node.priority,
                    result_json=None,
                    error=None,
                    created_at=now,
                    updated_at=now,
                    optimistic_version=0,
                )
                await store.insert_step(step_row)
            await scope.commit()
            refreshed = await store.get_workflow(workflow_id)
            assert refreshed is not None
            return self._workflow_view(refreshed)

    async def get_workflow(self, workflow_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_workflow(workflow_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Workflow {workflow_id!r} not found.", context={"workflow_id": workflow_id})
            return self._workflow_view(row)

    async def list_workflows(self, session_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_workflows(session_id)
            return tuple(self._workflow_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Steps
    # ------------------------------------------------------------------ #

    async def transition_step(self, *, step_id: str, target_state: str, expected_version: int | None = None) -> Any:
        try:
            target = StepState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown step state {target_state!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_step(step_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Step {step_id!r} not found.", context={"step_id": step_id})
            current = StepState(existing.state)
            if expected_version is not None and existing.optimistic_version != expected_version:
                raise AgentRuntimeStaleVersionError("Step optimistic version mismatch.", context={"step_id": step_id})
            StepLifecycle.transition(current, target)
            if current == target:
                return self._step_view(existing)
            updated = await store.update_step(
                step_id,
                state=target.value,
                optimistic_version=existing.optimistic_version + 1,
                expected_version=expected_version if expected_version is not None else existing.optimistic_version,
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Step optimistic version mismatch.", context={"step_id": step_id})
            await scope.commit()
            return self._step_view(updated)

    async def get_step(self, step_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_step(step_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Step {step_id!r} not found.", context={"step_id": step_id})
            return self._step_view(row)

    async def list_steps(self, workflow_id: str | None = None, run_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_steps(workflow_id, run_id)
            return tuple(self._step_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Checkpoints
    # ------------------------------------------------------------------ #

    async def create_checkpoint(
        self,
        *,
        run_id: str,
        state_snapshot: dict[str, Any] | None = None,
        task_id: str | None = None,
        workflow_id: str | None = None,
        step_id: str | None = None,
        seq: int | None = None,
    ) -> Any:
        payload = state_snapshot or {}
        h = canonical_hash(payload)
        # Determine seq if not provided: count existing for run_id
        async with self._scope_factory() as scope:
            store = scope.store()
            run = await store.get_run(run_id)
            if run is None:
                raise AgentRuntimeNotFoundError(f"Run {run_id!r} not found.", context={"run_id": run_id})
            if task_id is not None:
                t = await store.get_task(task_id)
                if t is None:
                    raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            if workflow_id is not None:
                wf = await store.get_workflow(workflow_id)
                if wf is None:
                    raise AgentRuntimeNotFoundError(f"Workflow {workflow_id!r} not found.", context={"workflow_id": workflow_id})
            if step_id is not None:
                s = await store.get_step(step_id)
                if s is None:
                    raise AgentRuntimeNotFoundError(f"Step {step_id!r} not found.", context={"step_id": step_id})
            if seq is None:
                existing = await store.list_checkpoints(run_id=run_id, task_id=task_id)
                # Filter same run scope seq = max+1
                max_seq = max((c.seq for c in existing), default=-1)
                seq = max_seq + 1
            checkpoint_id = _new_id()
            now = datetime.now(UTC)
            row = CheckpointRow(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                task_id=task_id,
                workflow_id=workflow_id,
                step_id=step_id,
                seq=seq,
                state_snapshot_json=_dump(payload),
                snapshot_hash=h,
                created_at=now,
            )
            # Check seq uniqueness per run_id (simple: ensure no duplicate seq for same run+task)
            existing_same_seq = [c for c in await store.list_checkpoints(run_id=run_id, task_id=task_id) if c.seq == seq]
            if existing_same_seq:
                raise AgentRuntimeValidationError(f"Checkpoint seq {seq} already exists for run {run_id!r}.", context={"run_id": run_id, "seq": seq})
            ok = await store.insert_checkpoint(row)
            if not ok:
                raise AgentRuntimeValidationError("Checkpoint id collision — retry.")
            # Optionally bind to task's checkpoint_id
            if task_id is not None:
                task = await store.get_task(task_id)
                if task is not None:
                    await store.update_task(task_id, checkpoint_id=checkpoint_id, optimistic_version=task.optimistic_version + 1, expected_version=task.optimistic_version)
            await scope.record_event(self._events.checkpoint_created(checkpoint_id, run_id))
            await scope.commit()
            inserted = await store.get_checkpoint(checkpoint_id)
            assert inserted is not None
            return self._checkpoint_view(inserted)

    async def get_checkpoint(self, checkpoint_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_checkpoint(checkpoint_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Checkpoint {checkpoint_id!r} not found.", context={"checkpoint_id": checkpoint_id})
            return self._checkpoint_view(row)

    async def list_checkpoints(self, run_id: str | None = None, task_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_checkpoints(run_id, task_id)
            return tuple(self._checkpoint_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Approvals
    # ------------------------------------------------------------------ #

    async def request_approval(
        self, *, task_id: str, requested_by: str = "system", payload: dict[str, Any] | None = None, run_id: str | None = None, expires_in_seconds: float | None = None
    ) -> Any:
        if not task_id.strip():
            raise AgentRuntimeValidationError("task_id cannot be blank.")
        payload = payload or {}
        async with self._scope_factory() as scope:
            store = scope.store()
            task = await store.get_task(task_id)
            if task is None:
                raise AgentRuntimeNotFoundError(f"Task {task_id!r} not found.", context={"task_id": task_id})
            # Task must be in a state that can wait for permission? For ergonomics, we transition task to WAITING_PERMISSION if possible
            current_task_state = TaskState(task.state)
            if current_task_state not in (TaskState.RUNNING, TaskState.WAITING_PERMISSION):
                raise AgentRuntimeValidationError(f"Task state {current_task_state.value} cannot request approval.", context={"task_id": task_id})
            approval_id = _new_id()
            now = datetime.now(UTC)
            expires_at = None
            if expires_in_seconds is not None:
                if expires_in_seconds <= 0:
                    raise AgentRuntimeValidationError("expires_in_seconds must be > 0.")
                from datetime import timedelta

                expires_at = now + timedelta(seconds=expires_in_seconds)
            row = ApprovalRow(
                approval_id=approval_id,
                task_id=task_id,
                run_id=run_id or task.run_id,
                requested_by=requested_by.strip() or "system",
                state=ApprovalState.PENDING.value,
                payload_json=_dump(payload),
                resolution_json=None,
                created_at=now,
                resolved_at=None,
                expires_at=expires_at,
            )
            ok = await store.insert_approval(row)
            if not ok:
                raise AgentRuntimeValidationError("Approval id collision — retry.")
            # Transition task to WAITING_PERMISSION if not already
            if current_task_state != TaskState.WAITING_PERMISSION:
                updated_task = await store.update_task(
                    task_id,
                    state=TaskState.WAITING_PERMISSION.value,
                    awaiting_approval_id=approval_id,
                    optimistic_version=task.optimistic_version + 1,
                    expected_version=task.optimistic_version,
                )
                if updated_task is None:
                    raise AgentRuntimeStaleVersionError("Task optimistic version mismatch.", context={"task_id": task_id})
                await scope.record_event(self._events.task_transitioned(task_id, current_task_state.value, TaskState.WAITING_PERMISSION.value))
            else:
                # Just bind approval id if not set
                if task.awaiting_approval_id != approval_id:
                    await store.update_task(
                        task_id,
                        awaiting_approval_id=approval_id,
                        optimistic_version=task.optimistic_version + 1,
                        expected_version=task.optimistic_version,
                    )
            await scope.record_event(self._events.approval_requested(approval_id, task_id))
            await scope.commit()
            inserted = await store.get_approval(approval_id)
            assert inserted is not None
            return self._approval_view(inserted)

    async def resolve_approval(self, *, approval_id: str, target_state: str, resolution: dict[str, Any] | None = None) -> Any:
        try:
            target = ApprovalState(target_state)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown approval state {target_state!r}.") from exc
        if target not in (ApprovalState.APPROVED, ApprovalState.DENIED, ApprovalState.EXPIRED):
            raise AgentRuntimeValidationError(f"Approval can only resolve to APPROVED/DENIED/EXPIRED, got {target_state!r}.")
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_approval(approval_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Approval {approval_id!r} not found.", context={"approval_id": approval_id})
            if existing.state != ApprovalState.PENDING.value:
                raise AgentRuntimeValidationError(f"Approval {approval_id!r} is already terminal {existing.state}.", context={"approval_id": approval_id})
            updated = await store.update_approval(
                approval_id, state=target.value, resolution_json=_dump(resolution or {}), expected_state=ApprovalState.PENDING.value
            )
            if updated is None:
                raise AgentRuntimeStaleVersionError("Approval optimistic version mismatch.", context={"approval_id": approval_id})
            # Transition task accordingly: APPROVED -> RUNNING, DENIED/EXPIRED -> FAILED or CANCELLED?
            task = await store.get_task(existing.task_id)
            if task is not None:
                task_state = TaskState(task.state)
                if target == ApprovalState.APPROVED:
                    if task_state == TaskState.WAITING_PERMISSION:
                        await store.update_task(
                            task.task_id,
                            state=TaskState.RUNNING.value,
                            awaiting_approval_id=None,
                            optimistic_version=task.optimistic_version + 1,
                            expected_version=task.optimistic_version,
                        )
                        await scope.record_event(self._events.task_transitioned(task.task_id, task_state.value, TaskState.RUNNING.value))
                elif target in (ApprovalState.DENIED, ApprovalState.EXPIRED):
                    # Denied/expired leads to FAILED (or CANCELLED if payload indicates cancellation)
                    await store.update_task(
                        task.task_id,
                        state=TaskState.FAILED.value,
                        error=f"approval {target.value.lower()}",
                        awaiting_approval_id=None,
                        optimistic_version=task.optimistic_version + 1,
                        expected_version=task.optimistic_version,
                        completed_at=datetime.now(UTC),
                    )
                    await scope.record_event(self._events.task_transitioned(task.task_id, task_state.value, TaskState.FAILED.value))
                    await scope.record_event(self._events.task_failed(task.task_id, f"approval {target.value.lower()}"))
            await scope.record_event(self._events.approval_resolved(approval_id, target.value))
            await scope.commit()
            refreshed = await store.get_approval(approval_id)
            assert refreshed is not None
            return self._approval_view(refreshed)

    async def get_approval(self, approval_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_approval(approval_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Approval {approval_id!r} not found.", context={"approval_id": approval_id})
            return self._approval_view(row)

    async def list_approvals(self, task_id: str | None = None, state: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_approvals(task_id, state)
            return tuple(self._approval_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Delegations
    # ------------------------------------------------------------------ #

    async def delegate_run(self, *, parent_run_id: str, child_run_id: str, metadata: dict[str, Any] | None = None) -> Any:
        if parent_run_id == child_run_id:
            raise AgentRuntimeValidationError("Delegation parent and child cannot be identical.")
        async with self._scope_factory() as scope:
            store = scope.store()
            parent = await store.get_run(parent_run_id)
            if parent is None:
                raise AgentRuntimeNotFoundError(f"Parent run {parent_run_id!r} not found.", context={"run_id": parent_run_id})
            child = await store.get_run(child_run_id)
            if child is None:
                raise AgentRuntimeNotFoundError(f"Child run {child_run_id!r} not found.", context={"run_id": child_run_id})
            if parent.session_id != child.session_id:
                raise AgentRuntimeValidationError("Delegation runs must share session.")
            # Enforce max_child_agents limit via parent budget
            parent_limits = AgentBudgetLimits(**_load(parent.budget_limits_json, {}))
            parent_usage = AgentBudgetUsage(**_load(parent.budget_usage_json, {}))
            if parent_limits.max_child_agents is not None and parent_usage.child_agents >= parent_limits.max_child_agents:
                raise AgentRuntimeValidationError("Parent max_child_agents exhausted.", context={"run_id": parent_run_id})
            delegation_id = _new_id()
            now = datetime.now(UTC)
            row = DelegationRow(
                delegation_id=delegation_id,
                parent_run_id=parent_run_id,
                child_run_id=child_run_id,
                status=DelegationStatus.PENDING.value,
                created_at=now,
                completed_at=None,
                metadata_json=_dump(metadata or {}),
            )
            ok = await store.insert_delegation(row)
            if not ok:
                raise AgentRuntimeValidationError("Delegation id collision — retry.")
            # Bump parent usage child_agents and transition parent to WAITING_CHILD if not already
            new_usage = parent_usage.model_copy(update={"child_agents": parent_usage.child_agents + 1})
            await store.update_run(
                parent_run_id,
                budget_usage_json=_dump(new_usage.model_dump()),
                optimistic_version=parent.optimistic_version + 1,
                expected_version=parent.optimistic_version,
            )
            # Also try to move parent loop to WAITING_CHILD if RUNNING
            parent_state = AgentLoopState(parent.state)
            if parent_state == AgentLoopState.RUNNING:
                try:
                    refreshed_parent = await store.get_run(parent_run_id)
                    if refreshed_parent is not None and AgentLoopState(refreshed_parent.state) == AgentLoopState.RUNNING:
                        await store.update_run(
                            parent_run_id,
                            state=AgentLoopState.WAITING_CHILD.value,
                            optimistic_version=refreshed_parent.optimistic_version + 1,
                            expected_version=refreshed_parent.optimistic_version,
                        )
                        await scope.record_event(self._events.run_transitioned(parent_run_id, parent_state.value, AgentLoopState.WAITING_CHILD.value))
                except Exception:
                    pass
            await scope.record_event(self._events.delegation_created(delegation_id, parent_run_id, child_run_id))
            await scope.commit()
            inserted = await store.get_delegation(delegation_id)
            assert inserted is not None
            return self._delegation_view(inserted)

    async def transition_delegation(self, *, delegation_id: str, target_status: str) -> Any:
        try:
            target = DelegationStatus(target_status)
        except ValueError as exc:
            raise AgentRuntimeValidationError(f"Unknown delegation status {target_status!r}.") from exc
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_delegation(delegation_id)
            if existing is None:
                raise AgentRuntimeNotFoundError(f"Delegation {delegation_id!r} not found.", context={"delegation_id": delegation_id})
            current = DelegationStatus(existing.status)
            # Validate via domain (but we just use allowed map)
            from ..domain.delegation import DelegationRecord

            # Create temporary domain object to validate transition
            tmp = DelegationRecord(
                delegation_id=existing.delegation_id,
                parent_run_id=existing.parent_run_id,
                child_run_id=existing.child_run_id,
                status=current,
                created_at=_as_utc(existing.created_at) or datetime.now(UTC),
                completed_at=_as_utc(existing.completed_at),
                metadata=_load(existing.metadata_json, {}),
            )
            tmp.transition_to(target)  # will raise if illegal
            updated = await store.update_delegation(delegation_id, status=target.value)
            if updated is None:
                raise AgentRuntimeNotFoundError(f"Delegation {delegation_id!r} not found.", context={"delegation_id": delegation_id})
            await scope.record_event(self._events.delegation_transitioned(delegation_id, target.value))
            # If terminal, try to unblock parent: WAITING_CHILD -> RUNNING
            if target in (DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED):
                parent = await store.get_run(existing.parent_run_id)
                if parent is not None and parent.state == AgentLoopState.WAITING_CHILD.value:
                    # Check if any other delegations still pending/running for this parent
                    siblings = await store.list_delegations(parent_run_id=existing.parent_run_id)
                    still_blocking = any(
                        s.status in (DelegationStatus.PENDING.value, DelegationStatus.RUNNING.value) and s.delegation_id != delegation_id
                        for s in siblings
                    )
                    if not still_blocking:
                        await store.update_run(
                            existing.parent_run_id,
                            state=AgentLoopState.RUNNING.value,
                            optimistic_version=parent.optimistic_version + 1,
                            expected_version=parent.optimistic_version,
                        )
                        await scope.record_event(self._events.run_transitioned(existing.parent_run_id, AgentLoopState.WAITING_CHILD.value, AgentLoopState.RUNNING.value))
            await scope.commit()
            refreshed = await store.get_delegation(delegation_id)
            assert refreshed is not None
            return self._delegation_view(refreshed)

    async def get_delegation(self, delegation_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_delegation(delegation_id)
            if row is None:
                raise AgentRuntimeNotFoundError(f"Delegation {delegation_id!r} not found.", context={"delegation_id": delegation_id})
            return self._delegation_view(row)

    async def list_delegations(self, parent_run_id: str | None = None, child_run_id: str | None = None) -> tuple[Any, ...]:
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_delegations(parent_run_id, child_run_id)
            return tuple(self._delegation_view(r) for r in rows)
