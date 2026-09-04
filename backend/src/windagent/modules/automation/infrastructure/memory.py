"""In-memory Automation store and transaction scope for unit tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from windagent.kernel.events import EventEnvelope

from ..application.models import ToolRow, ToolRunRow
from ..application.ports import AutomationStore


class InMemoryAutomationStore(AutomationStore):
    def __init__(self) -> None:
        self.tools: dict[str, ToolRow] = {}
        self.tools_by_name: dict[str, str] = {}
        self.runs: dict[str, ToolRunRow] = {}
        self.runs_by_invocation: dict[str, str] = {}
        self.events: list[EventEnvelope] = []

    # -- tools ---------------------------------------------------------------
    async def insert_tool(self, row: ToolRow) -> bool:
        if row.name in self.tools_by_name:
            return False
        if row.tool_id in self.tools:
            return False
        self.tools[row.tool_id] = row
        self.tools_by_name[row.name] = row.tool_id
        return True

    async def get_tool(self, tool_id: str) -> ToolRow | None:
        return self.tools.get(tool_id)

    async def get_tool_by_name(self, name: str) -> ToolRow | None:
        tool_id = self.tools_by_name.get(name)
        if tool_id is None:
            return None
        return self.tools.get(tool_id)

    async def list_tools(
        self, *, capability: str | None = None, runtime_type: str | None = None, enabled_only: bool = False
    ) -> tuple[ToolRow, ...]:
        rows = list(self.tools.values())
        if capability is not None:
            rows = [r for r in rows if r.capability == capability]
        if runtime_type is not None:
            rows = [r for r in rows if r.runtime_type == runtime_type]
        if enabled_only:
            rows = [r for r in rows if r.enabled]
        return tuple(sorted(rows, key=lambda r: r.name))

    async def update_tool(
        self,
        tool_id: str,
        *,
        description: str | None = None,
        version: str | None = None,
        risk_level: str | None = None,
        capability: str | None = None,
        runtime_type: str | None = None,
        enabled: bool | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> ToolRow | None:
        existing = self.tools.get(tool_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = ToolRow(
            tool_id=existing.tool_id,
            name=existing.name,
            description=description if description is not None else existing.description,
            version=version if version is not None else existing.version,
            risk_level=risk_level if risk_level is not None else existing.risk_level,
            capability=capability if capability is not None else existing.capability,
            runtime_type=runtime_type if runtime_type is not None else existing.runtime_type,
            side_effect_class=existing.side_effect_class,
            is_idempotent=existing.is_idempotent,
            is_destructive=existing.is_destructive,
            is_reversible=existing.is_reversible,
            timeout_seconds=existing.timeout_seconds,
            required_permissions_json=existing.required_permissions_json,
            sandbox_requirement=existing.sandbox_requirement,
            artifact_outputs_json=existing.artifact_outputs_json,
            retry_eligible=existing.retry_eligible,
            redaction_policy=existing.redaction_policy,
            parameters_schema_json=existing.parameters_schema_json,
            output_schema_json=existing.output_schema_json,
            enabled=enabled if enabled is not None else existing.enabled,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
        )
        self.tools[tool_id] = updated
        return updated

    async def delete_tool(self, tool_id: str) -> bool:
        existing = self.tools.pop(tool_id, None)
        if existing is None:
            return False
        self.tools_by_name.pop(existing.name, None)
        return True

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: ToolRunRow) -> bool:
        if row.run_id in self.runs:
            return False
        self.runs[row.run_id] = row
        self.runs_by_invocation[row.invocation_id] = row.run_id
        return True

    async def get_run(self, run_id: str) -> ToolRunRow | None:
        return self.runs.get(run_id)

    async def get_run_by_invocation(self, invocation_id: str) -> ToolRunRow | None:
        run_id = self.runs_by_invocation.get(invocation_id)
        if run_id is None:
            return None
        return self.runs.get(run_id)

    async def list_runs(
        self, *, tool_name: str | None = None, status: str | None = None, limit: int = 50
    ) -> tuple[ToolRunRow, ...]:
        rows = list(self.runs.values())
        if tool_name is not None:
            rows = [r for r in rows if r.tool_name == tool_name]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        rows.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return tuple(rows[:limit])

    async def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        result_json: str | None = None,
        error: str | None = None,
        execution_time_ms: int | None = None,
        completed_at: object | None = None,
    ) -> ToolRunRow | None:
        existing = self.runs.get(run_id)
        if existing is None:
            return None
        updated = ToolRunRow(
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
            status=status if status is not None else existing.status,
            result_json=result_json if result_json is not None else existing.result_json,
            error=error if error is not None else existing.error,
            execution_time_ms=execution_time_ms if execution_time_ms is not None else existing.execution_time_ms,
            policy_decision_json=existing.policy_decision_json,
            created_at=existing.created_at,
            completed_at=completed_at if isinstance(completed_at, datetime) else existing.completed_at,
        )
        self.runs[run_id] = updated
        return updated


class InMemoryTransactionScope:
    def __init__(self, store: InMemoryAutomationStore) -> None:
        self._store = store
        self._pending: list[tuple[EventEnvelope, str | None]] = []

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._pending.clear()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None
    ) -> bool:
        if exc_type is not None:
            self._pending.clear()
        return False

    def store(self) -> InMemoryAutomationStore:
        return self._store

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._pending.append((envelope, deduplication_key))
        return True

    async def commit(self) -> None:
        for envelope, _ in self._pending:
            self._store.events.append(envelope)
        self._pending.clear()


def memory_scope_factory(store: InMemoryAutomationStore) -> Callable[[], InMemoryTransactionScope]:
    return lambda: InMemoryTransactionScope(store)
