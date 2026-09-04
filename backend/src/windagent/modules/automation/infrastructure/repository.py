"""SQL adapter for the Automation store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.models import ToolRow, ToolRunRow
from ..application.ports import AutomationStore
from .tables import tool_runs_table, tools_table

STORE_REPOSITORY_NAME = "automation_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def make_store(session: AsyncSession) -> SqlAutomationStore:
    return SqlAutomationStore(session)


class SqlAutomationStore(AutomationStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- tools ---------------------------------------------------------------
    async def insert_tool(self, row: ToolRow) -> bool:
        exists = await self._session.execute(select(tools_table.c.tool_id).where(tools_table.c.tool_id == row.tool_id))
        if exists.first() is not None:
            return False
        name_exists = await self._session.execute(select(tools_table.c.name).where(tools_table.c.name == row.name))
        if name_exists.first() is not None:
            return False
        await self._session.execute(
            insert(tools_table).values(
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
                required_permissions_json=row.required_permissions_json,
                sandbox_requirement=row.sandbox_requirement,
                artifact_outputs_json=row.artifact_outputs_json,
                retry_eligible=row.retry_eligible,
                redaction_policy=row.redaction_policy,
                parameters_schema_json=row.parameters_schema_json,
                output_schema_json=row.output_schema_json,
                enabled=row.enabled,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
            )
        )
        return True

    async def get_tool(self, tool_id: str) -> ToolRow | None:
        result = await self._session.execute(select(tools_table).where(tools_table.c.tool_id == tool_id))
        row = result.first()
        return _tool_from_row(row) if row else None

    async def get_tool_by_name(self, name: str) -> ToolRow | None:
        result = await self._session.execute(select(tools_table).where(tools_table.c.name == name))
        row = result.first()
        return _tool_from_row(row) if row else None

    async def list_tools(
        self, *, capability: str | None = None, runtime_type: str | None = None, enabled_only: bool = False
    ) -> tuple[ToolRow, ...]:
        stmt = select(tools_table)
        if capability is not None:
            stmt = stmt.where(tools_table.c.capability == capability)
        if runtime_type is not None:
            stmt = stmt.where(tools_table.c.runtime_type == runtime_type)
        if enabled_only:
            stmt = stmt.where(tools_table.c.enabled.is_(True))
        stmt = stmt.order_by(tools_table.c.name.asc())
        result = await self._session.execute(stmt)
        return tuple(_tool_from_row(row) for row in result.all())

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
        existing = await self.get_tool(tool_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if description is not None:
            values["description"] = description
        if version is not None:
            values["version"] = version
        if risk_level is not None:
            values["risk_level"] = risk_level
        if capability is not None:
            values["capability"] = capability
        if runtime_type is not None:
            values["runtime_type"] = runtime_type
        if enabled is not None:
            values["enabled"] = enabled
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if expected_version is not None:
            outcome = await self._session.execute(
                update(tools_table)
                .where(tools_table.c.tool_id == tool_id, tools_table.c.optimistic_version == expected_version)
                .values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(tools_table).where(tools_table.c.tool_id == tool_id).values(**values))
        return await self.get_tool(tool_id)

    async def delete_tool(self, tool_id: str) -> bool:
        existing = await self.get_tool(tool_id)
        if existing is None:
            return False
        await self._session.execute(tools_table.delete().where(tools_table.c.tool_id == tool_id))
        return True

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: ToolRunRow) -> bool:
        exists = await self._session.execute(select(tool_runs_table.c.run_id).where(tool_runs_table.c.run_id == row.run_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(tool_runs_table).values(
                run_id=row.run_id,
                tool_name=row.tool_name,
                tool_version=row.tool_version,
                invocation_id=row.invocation_id,
                params_json=row.params_json,
                workspace_root=row.workspace_root,
                actor_id=row.actor_id,
                correlation_id=row.correlation_id,
                causation_id=row.causation_id,
                trace_id=row.trace_id,
                runtime_type=row.runtime_type,
                status=row.status,
                result_json=row.result_json,
                error=row.error,
                execution_time_ms=row.execution_time_ms,
                policy_decision_json=row.policy_decision_json,
                created_at=_as_utc(row.created_at),
                completed_at=_as_utc(row.completed_at),
            )
        )
        return True

    async def get_run(self, run_id: str) -> ToolRunRow | None:
        result = await self._session.execute(select(tool_runs_table).where(tool_runs_table.c.run_id == run_id))
        row = result.first()
        return _run_from_row(row) if row else None

    async def get_run_by_invocation(self, invocation_id: str) -> ToolRunRow | None:
        result = await self._session.execute(
            select(tool_runs_table).where(tool_runs_table.c.invocation_id == invocation_id)
        )
        row = result.first()
        return _run_from_row(row) if row else None

    async def list_runs(
        self, *, tool_name: str | None = None, status: str | None = None, limit: int = 50
    ) -> tuple[ToolRunRow, ...]:
        stmt = select(tool_runs_table)
        if tool_name is not None:
            stmt = stmt.where(tool_runs_table.c.tool_name == tool_name)
        if status is not None:
            stmt = stmt.where(tool_runs_table.c.status == status)
        stmt = stmt.order_by(tool_runs_table.c.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return tuple(_run_from_row(row) for row in result.all())

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
        existing = await self.get_run(run_id)
        if existing is None:
            return None
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
        if result_json is not None:
            values["result_json"] = result_json
        if error is not None:
            values["error"] = error
        if execution_time_ms is not None:
            values["execution_time_ms"] = execution_time_ms
        if isinstance(completed_at, datetime):
            values["completed_at"] = _as_utc(completed_at)
        if not values:
            return existing
        await self._session.execute(update(tool_runs_table).where(tool_runs_table.c.run_id == run_id).values(**values))
        return await self.get_run(run_id)


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):  # pragma: no cover
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None
    ) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    def store(self) -> AutomationStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(AutomationStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(envelope, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    return lambda: SqlTransactionScope(database)


def _tool_from_row(row: Any) -> ToolRow:
    return ToolRow(
        tool_id=str(row.tool_id),
        name=str(row.name),
        description=str(row.description),
        version=str(row.version),
        risk_level=str(row.risk_level),
        capability=str(row.capability),
        runtime_type=str(row.runtime_type),
        side_effect_class=str(row.side_effect_class),
        is_idempotent=bool(row.is_idempotent),
        is_destructive=bool(row.is_destructive),
        is_reversible=bool(row.is_reversible),
        timeout_seconds=int(row.timeout_seconds),
        required_permissions_json=str(row.required_permissions_json),
        sandbox_requirement=str(row.sandbox_requirement),
        artifact_outputs_json=str(row.artifact_outputs_json),
        retry_eligible=bool(row.retry_eligible),
        redaction_policy=str(row.redaction_policy),
        parameters_schema_json=str(row.parameters_schema_json),
        output_schema_json=str(row.output_schema_json),
        enabled=bool(row.enabled),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
    )


def _run_from_row(row: Any) -> ToolRunRow:
    return ToolRunRow(
        run_id=str(row.run_id),
        tool_name=str(row.tool_name),
        tool_version=str(row.tool_version),
        invocation_id=str(row.invocation_id),
        params_json=str(row.params_json),
        workspace_root=str(row.workspace_root),
        actor_id=str(row.actor_id) if row.actor_id is not None else None,
        correlation_id=str(row.correlation_id) if row.correlation_id is not None else None,
        causation_id=str(row.causation_id) if row.causation_id is not None else None,
        trace_id=str(row.trace_id) if row.trace_id is not None else None,
        runtime_type=str(row.runtime_type),
        status=str(row.status),
        result_json=str(row.result_json) if row.result_json is not None else None,
        error=str(row.error) if row.error is not None else None,
        execution_time_ms=int(row.execution_time_ms),
        policy_decision_json=str(row.policy_decision_json) if row.policy_decision_json is not None else None,
        created_at=_as_utc(row.created_at),
        completed_at=_as_utc(row.completed_at),
    )
