"""Repository port for Automation persistence."""

from __future__ import annotations

from typing import Protocol

from windagent.kernel.events import EventEnvelope

from .models import ToolRow, ToolRunRow


class AutomationStore(Protocol):
    """Durable port — one method per aggregate table."""

    # -- tools ---------------------------------------------------------------
    async def insert_tool(self, row: ToolRow) -> bool: ...
    async def get_tool(self, tool_id: str) -> ToolRow | None: ...
    async def get_tool_by_name(self, name: str) -> ToolRow | None: ...
    async def list_tools(
        self, *, capability: str | None = None, runtime_type: str | None = None, enabled_only: bool = False
    ) -> tuple[ToolRow, ...]: ...
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
    ) -> ToolRow | None: ...
    async def delete_tool(self, tool_id: str) -> bool: ...

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: ToolRunRow) -> bool: ...
    async def get_run(self, run_id: str) -> ToolRunRow | None: ...
    async def get_run_by_invocation(self, invocation_id: str) -> ToolRunRow | None: ...
    async def list_runs(
        self, *, tool_name: str | None = None, status: str | None = None, limit: int = 50
    ) -> tuple[ToolRunRow, ...]: ...
    async def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        result_json: str | None = None,
        error: str | None = None,
        execution_time_ms: int | None = None,
        completed_at: object | None = None,
    ) -> ToolRunRow | None: ...


class TransactionScope(Protocol):
    """Bounded UnitOfWork scope + outbox event writer."""

    def store(self) -> AutomationStore: ...
    async def record_event(
        self, envelope: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool: ...
    async def commit(self) -> None: ...
    async def __aenter__(self) -> TransactionScope: ...
    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None
    ) -> bool: ...
