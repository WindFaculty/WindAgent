"""Application service orchestrating Automation aggregates (Phase 12).

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

from ..domain.definition import RuntimeType, ToolDefinition, ToolRiskLevel
from ..domain.errors import (
    AutomationConflictError,
    AutomationNotFoundError,
    AutomationValidationError,
)
from ..domain.invocation import ToolExecutionContext, ToolInvocation
from .events import AutomationEventFactory
from .executor import ToolExecutor
from .models import ToolRow, ToolRunRow
from .ports import TransactionScope
from .registry import RuntimeRegistry, ToolRegistry


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


def _definition_to_row(definition: ToolDefinition, tool_id: str, created_at: datetime | None = None, updated_at: datetime | None = None, optimistic_version: int = 0) -> ToolRow:
    now = datetime.now(UTC)
    return ToolRow(
        tool_id=tool_id,
        name=definition.name,
        description=definition.description,
        version=definition.version,
        risk_level=definition.risk_level.value,
        capability=definition.capability,
        runtime_type=definition.runtime_type.value,
        side_effect_class=definition.side_effect_class,
        is_idempotent=definition.is_idempotent,
        is_destructive=definition.is_destructive,
        is_reversible=definition.is_reversible,
        timeout_seconds=int(definition.timeout_seconds),
        required_permissions_json=_dump(list(definition.required_permissions)),
        sandbox_requirement=definition.sandbox_requirement,
        artifact_outputs_json=_dump(list(definition.artifact_outputs)),
        retry_eligible=definition.retry_eligible,
        redaction_policy=definition.redaction_policy,
        parameters_schema_json=_dump(definition.parameters_schema),
        output_schema_json=_dump(definition.output_schema),
        enabled=definition.enabled,
        created_at=created_at or now,
        updated_at=updated_at or now,
        optimistic_version=optimistic_version,
    )


def _row_to_definition(row: ToolRow) -> ToolDefinition:
    return ToolDefinition(
        name=row.name,
        description=row.description,
        version=row.version,
        risk_level=ToolRiskLevel(row.risk_level),
        capability=row.capability,
        runtime_type=RuntimeType(row.runtime_type),
        side_effect_class=row.side_effect_class,
        is_idempotent=row.is_idempotent,
        is_destructive=row.is_destructive,
        is_reversible=row.is_reversible,
        timeout_seconds=float(row.timeout_seconds),
        required_permissions=tuple(_load(row.required_permissions_json, [])),
        sandbox_requirement=row.sandbox_requirement,
        artifact_outputs=tuple(_load(row.artifact_outputs_json, [])),
        retry_eligible=row.retry_eligible,
        redaction_policy=row.redaction_policy,
        parameters_schema=_load(row.parameters_schema_json, {}),
        output_schema=_load(row.output_schema_json, {}),
        enabled=row.enabled,
    )


def _row_to_view(row: ToolRow) -> Any:
    from .models import ToolView

    return ToolView(
        tool_id=row.tool_id,
        name=row.name,
        description=row.description,
        version=row.version,
        risk_level=row.risk_level,
        capability=row.capability,
        runtime_type=row.runtime_type,
        side_effect_class=row.side_effect_class,
        is_idempotent=row.is_idempotent,
        is_destructive=row.is_destructive,
        is_reversible=row.is_reversible,
        timeout_seconds=row.timeout_seconds,
        required_permissions=tuple(_load(row.required_permissions_json, [])),
        sandbox_requirement=row.sandbox_requirement,
        artifact_outputs=tuple(_load(row.artifact_outputs_json, [])),
        retry_eligible=row.retry_eligible,
        redaction_policy=row.redaction_policy,
        parameters_schema=_load(row.parameters_schema_json, {}),
        output_schema=_load(row.output_schema_json, {}),
        enabled=row.enabled,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=row.optimistic_version,
    )


def _run_row_to_view(row: ToolRunRow) -> Any:
    from .models import ToolRunView

    return ToolRunView(
        run_id=row.run_id,
        tool_name=row.tool_name,
        tool_version=row.tool_version,
        invocation_id=row.invocation_id,
        params=_load(row.params_json, {}),
        workspace_root=row.workspace_root,
        actor_id=row.actor_id,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        trace_id=row.trace_id,
        runtime_type=row.runtime_type,
        status=row.status,
        result=_load(row.result_json, None) if row.result_json else None,
        error=row.error,
        execution_time_ms=row.execution_time_ms,
        policy_decision=_load(row.policy_decision_json, None) if row.policy_decision_json else None,
        created_at=_as_utc(row.created_at),
        completed_at=_as_utc(row.completed_at),
    )


class AutomationService:
    """Orchestrates durable tool registry + execution runs."""

    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        tool_registry: ToolRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        executor: ToolExecutor | None = None,
        clock: Clock,
        event_factory: AutomationEventFactory,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._clock = clock
        self._events = event_factory
        self._telemetry = telemetry
        self._tool_registry = tool_registry or ToolRegistry()
        self._runtime_registry = runtime_registry or RuntimeRegistry()
        self._executor = executor
        # When executor provided externally (e.g., with custom policy engine), honor it;
        # otherwise create one wired to the registries (policy engine is injected later
        # via AutomationServices composition).
        if self._executor is None:
            self._executor = ToolExecutor(
                tool_registry=self._tool_registry,
                runtime_registry=self._runtime_registry,
                policy_engine=None,
            )

    def bind_executor(self, executor: ToolExecutor) -> None:
        self._executor = executor

    def bind_registries(self, tool_registry: ToolRegistry, runtime_registry: RuntimeRegistry) -> None:
        self._tool_registry = tool_registry
        self._runtime_registry = runtime_registry
        # rebind executor's internal registries as well if using the service-owned executor
        if self._executor is not None:
            # recreate with same policy engine but new registries
            policy_engine = getattr(self._executor, "_policy_engine", None)
            self._executor = ToolExecutor(
                tool_registry=tool_registry, runtime_registry=runtime_registry, policy_engine=policy_engine
            )

    # ------------------------------------------------------------------ #
    # Registry ops
    # ------------------------------------------------------------------ #

    async def register_tool(self, definition: ToolDefinition) -> Any:
        if not definition.name.strip():
            raise AutomationValidationError("tool name cannot be blank.")
        # Check duplicate in store
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_tool_by_name(definition.name)
            if existing is not None:
                raise AutomationConflictError(f"tool [{definition.name}] already registered", context={"tool_name": definition.name})
            tool_id = _new_id()
            row = _definition_to_row(definition, tool_id)
            ok = await store.insert_tool(row)
            if not ok:
                raise AutomationConflictError(f"tool [{definition.name}] collision", context={"tool_name": definition.name})
            try:
                self._tool_registry.register(definition)
            except AutomationConflictError:
                # Mirror durability; should not happen because we checked, but handle
                pass
            await scope.record_event(self._events.tool_registered(tool_id, definition.name))
            await scope.commit()
            inserted = await store.get_tool(tool_id)
            assert inserted is not None
            return _row_to_view(inserted)

    async def update_tool(
        self,
        *,
        tool_id: str,
        description: str | None = None,
        version: str | None = None,
        risk_level: str | None = None,
        capability: str | None = None,
        runtime_type: str | None = None,
        enabled: bool | None = None,
        expected_version: int | None = None,
    ) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_tool(tool_id)
            if existing is None:
                raise AutomationNotFoundError(f"tool {tool_id!r} not found", context={"tool_id": tool_id})
            # Validate runtime type if provided
            if runtime_type is not None:
                try:
                    RuntimeType(runtime_type)
                except ValueError as exc:
                    raise AutomationValidationError(f"unknown runtime_type {runtime_type!r}") from exc
            if risk_level is not None:
                try:
                    ToolRiskLevel(risk_level)
                except ValueError as exc:
                    raise AutomationValidationError(f"unknown risk_level {risk_level!r}") from exc
            updated = await store.update_tool(
                tool_id,
                description=description,
                version=version,
                risk_level=risk_level,
                capability=capability,
                runtime_type=runtime_type,
                enabled=enabled,
                optimistic_version=(existing.optimistic_version + 1) if expected_version is not None else None,
                expected_version=expected_version,
            )
            if updated is None:
                raise AutomationConflictError("tool optimistic version mismatch", context={"tool_id": tool_id})
            # Reflect in in-memory registry
            try:
                new_def = _row_to_definition(updated)
                # Re-register (override)
                self._tool_registry.register(new_def, override_collision=True)
            except Exception:
                pass
            await scope.record_event(self._events.tool_updated(tool_id, updated.name))
            await scope.commit()
            return _row_to_view(updated)

    async def deregister_tool(self, tool_id: str) -> None:
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_tool(tool_id)
            if existing is None:
                raise AutomationNotFoundError(f"tool {tool_id!r} not found", context={"tool_id": tool_id})
            ok = await store.delete_tool(tool_id)
            if not ok:
                raise AutomationNotFoundError(f"tool {tool_id!r} not found", context={"tool_id": tool_id})
            self._tool_registry.remove(existing.name)
            await scope.record_event(self._events.tool_deregistered(tool_id, existing.name))
            await scope.commit()

    async def get_tool(self, tool_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_tool(tool_id)
            if row is None:
                raise AutomationNotFoundError(f"tool {tool_id!r} not found", context={"tool_id": tool_id})
            return _row_to_view(row)

    async def get_tool_by_name(self, name: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_tool_by_name(name)
            if row is None:
                raise AutomationNotFoundError(f"tool [{name}] not found", context={"tool_name": name})
            return _row_to_view(row)

    async def list_tools(self, *, capability: str | None = None, runtime_type: str | None = None, enabled_only: bool = False) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_tools(capability=capability, runtime_type=runtime_type, enabled_only=enabled_only)
            return tuple(_row_to_view(r) for r in rows)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    async def execute_tool(
        self,
        *,
        tool_name: str,
        params: dict[str, Any] | None = None,
        workspace_root: str = "/tmp",
        actor_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        trace_id: str | None = None,
        user_approved: bool = False,
        invocation_id: str | None = None,
    ) -> Any:
        # Ensure tool exists in store (authoritative) and hydrate registry if needed
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_tool_by_name(tool_name)
            if row is None:
                raise AutomationNotFoundError(f"tool [{tool_name}] not registered", context={"tool_name": tool_name})
            if row.name not in self._tool_registry._tools:
                try:
                    self._tool_registry.register(_row_to_definition(row))
                except Exception:
                    pass
            runtime_type = row.runtime_type
            tool_version = row.version

        invocation = ToolInvocation(tool_name=tool_name, params=params or {}, call_id=invocation_id or f"call_{_new_id()[:12]}")
        ctx = ToolExecutionContext(
            workspace_root=workspace_root,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id,
            user_approved=user_approved,
        )

        # Create run row as pending
        run_id = _new_id()
        now = datetime.now(UTC)
        run_row = ToolRunRow(
            run_id=run_id,
            tool_name=tool_name,
            tool_version=tool_version,
            invocation_id=invocation.call_id,
            params_json=_dump(params or {}),
            workspace_root=workspace_root,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id,
            runtime_type=runtime_type,
            status="pending",
            result_json=None,
            error=None,
            execution_time_ms=0,
            policy_decision_json=None,
            created_at=now,
            completed_at=None,
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            await store.insert_run(run_row)
            await scope.record_event(self._events.tool_invoked(run_id, tool_name, invocation.call_id))
            await scope.commit()

        # Dispatch via executor
        assert self._executor is not None
        # Build a ctx that carries approval etc for executor's policy gate
        # Executor will return (result, decision) or raise policy denial which try_execute handles
        from ..domain.errors import (
            AutomationPolicyApprovalRequiredError,
            AutomationPolicyDeniedError,
        )

        started_at = datetime.now(UTC)
        try:
            result, decision = await self._executor.execute(invocation, ctx)
            decision_payload = {"effect": decision.effect.value, "reason": decision.reason, "policy_id": decision.policy_id}
            # Success run
            completed_at = datetime.now(UTC)
            exec_ms = int(result.execution_time_ms or (completed_at - started_at).total_seconds() * 1000)
            async with self._scope_factory() as scope:
                store = scope.store()
                await store.update_run(
                    run_id,
                    status="succeeded" if result.success else "failed",
                    result_json=_dump(result.data) if result.data is not None else None,
                    error=result.error,
                    execution_time_ms=exec_ms,
                    completed_at=completed_at,
                )
                # Record policy + result event atomically
                row_after = await store.get_run(run_id)
                if row_after is not None:
                    # update policy decision payload by re-writing run with decision json
                    # we stash decision as JSON in a second update (or we could store inline; for now patch via direct store mutation for in-memory compat)
                    # For SQL we would update policy_decision_json in same row; do an explicit low-level update
                    # Use the store's update_run doesn't support policy_decision, so we patch both memory and SQL directly
                    if isinstance(store, object):
                        # Try to persist policy decision json
                        try:
                            from ..infrastructure.repository import SqlAutomationStore

                            if isinstance(store, SqlAutomationStore):
                                # Direct SQL update for policy_decision
                                from sqlalchemy import update as sa_update

                                from ..infrastructure.tables import tool_runs_table

                                await store._session.execute(
                                    sa_update(tool_runs_table)
                                    .where(tool_runs_table.c.run_id == run_id)
                                    .values(policy_decision_json=_dump(decision_payload))
                                )
                            else:
                                # InMemory: mutate dict directly
                                mr = getattr(store, "runs", None)
                                if isinstance(mr, dict) and run_id in mr:
                                    existing = mr[run_id]
                                    mr[run_id] = ToolRunRow(
                                        run_id=existing.run_id,
                                        tool_name=existing.tool_name,
                                        tool_version=existing.tool_version,
                                        invocation_id=existing.invocation_id,
                                        params_json=existing.params_json,
                                        workspace_root=existing.workspace_root,
                                        actor_id=existing.actor_id,
                                        correlation_id=existing.correlation_id,
                                        causation_id=existing.causation_id,
                                        trace_id=existing.trace_id,
                                        runtime_type=existing.runtime_type,
                                        status=existing.status,
                                        result_json=existing.result_json,
                                        error=existing.error,
                                        execution_time_ms=existing.execution_time_ms,
                                        policy_decision_json=_dump(decision_payload),
                                        created_at=existing.created_at,
                                        completed_at=existing.completed_at,
                                    )
                        except Exception:
                            pass
                if result.success:
                    await scope.record_event(self._events.tool_succeeded(run_id, tool_name, exec_ms))
                else:
                    await scope.record_event(self._events.tool_failed(run_id, tool_name, result.error))
                await scope.commit()
            # Fetch final view
            async with self._scope_factory() as scope:
                store = scope.store()
                final = await store.get_run(run_id)
                assert final is not None
                return _run_row_to_view(final)
        except (AutomationPolicyDeniedError, AutomationPolicyApprovalRequiredError) as ex:
            # Policy denial path
            status = "denied" if isinstance(ex, AutomationPolicyDeniedError) else "approval_required"
            decision_payload = {"effect": "deny" if status == "denied" else "require_approval", "reason": str(ex), "policy_id": str(ex.context.get("policy_id", "")) if ex.context else None}
            completed_at = datetime.now(UTC)
            async with self._scope_factory() as scope:
                store = scope.store()
                await store.update_run(run_id, status=status, error=str(ex), execution_time_ms=0, completed_at=completed_at)
                # persist policy decision
                try:
                    from ..infrastructure.repository import SqlAutomationStore

                    if isinstance(store, SqlAutomationStore):
                        from sqlalchemy import update as sa_update

                        from ..infrastructure.tables import tool_runs_table

                        await store._session.execute(
                            sa_update(tool_runs_table)
                            .where(tool_runs_table.c.run_id == run_id)
                            .values(policy_decision_json=_dump(decision_payload))
                        )
                    else:
                        mr = getattr(store, "runs", None)
                        if isinstance(mr, dict) and run_id in mr:
                            existing = mr[run_id]
                            mr[run_id] = ToolRunRow(
                                run_id=existing.run_id,
                                tool_name=existing.tool_name,
                                tool_version=existing.tool_version,
                                invocation_id=existing.invocation_id,
                                params_json=existing.params_json,
                                workspace_root=existing.workspace_root,
                                actor_id=existing.actor_id,
                                correlation_id=existing.correlation_id,
                                causation_id=existing.causation_id,
                                trace_id=existing.trace_id,
                                runtime_type=existing.runtime_type,
                                status=existing.status,
                                result_json=existing.result_json,
                                error=existing.error,
                                execution_time_ms=existing.execution_time_ms,
                                policy_decision_json=_dump(decision_payload),
                                created_at=existing.created_at,
                                completed_at=existing.completed_at,
                            )
                except Exception:
                    pass
                await scope.record_event(self._events.tool_denied(run_id, tool_name, str(ex)))
                await scope.commit()
            async with self._scope_factory() as scope:
                store = scope.store()
                final = await store.get_run(run_id)
                assert final is not None
                # Raise again so API can map to 403/409 appropriately, but also return view for job handler
                # For direct service call we return the view; handlers can check status.
                # To preserve original raise semantics for callers expecting exception, re-raise.
                raise
        except Exception as ex:
            completed_at = datetime.now(UTC)
            async with self._scope_factory() as scope:
                store = scope.store()
                await store.update_run(run_id, status="failed", error=str(ex), execution_time_ms=0, completed_at=completed_at)
                await scope.record_event(self._events.tool_failed(run_id, tool_name, str(ex)))
                await scope.commit()
            raise

    async def get_run(self, run_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_run(run_id)
            if row is None:
                raise AutomationNotFoundError(f"run {run_id!r} not found", context={"run_id": run_id})
            return _run_row_to_view(row)

    async def get_run_by_invocation(self, invocation_id: str) -> Any:
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_run_by_invocation(invocation_id)
            if row is None:
                raise AutomationNotFoundError(f"run for invocation {invocation_id!r} not found", context={"invocation_id": invocation_id})
            return _run_row_to_view(row)

    async def list_runs(self, *, tool_name: str | None = None, status: str | None = None, limit: int = 50) -> tuple[Any, ...]:  # type: ignore[return]
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_runs(tool_name=tool_name, status=status, limit=limit)
            return tuple(_run_row_to_view(r) for r in rows)
