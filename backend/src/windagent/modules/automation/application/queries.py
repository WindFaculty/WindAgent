"""Immutable Automation queries."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import ToolRunView, ToolView


@dataclass(frozen=True, slots=True)
class GetTool(Query[ToolView]):
    tool_id: str


@dataclass(frozen=True, slots=True)
class GetToolByName(Query[ToolView]):
    name: str


@dataclass(frozen=True, slots=True)
class ListTools(Query[tuple[ToolView, ...]]):
    capability: str | None = None
    runtime_type: str | None = None
    enabled_only: bool = False


@dataclass(frozen=True, slots=True)
class GetToolRun(Query[ToolRunView]):
    run_id: str


@dataclass(frozen=True, slots=True)
class GetToolRunByInvocation(Query[ToolRunView]):
    invocation_id: str


@dataclass(frozen=True, slots=True)
class ListToolRuns(Query[tuple[ToolRunView, ...]]):
    tool_name: str | None = None
    status: str | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ListRuntimeTypes(Query[tuple[str, ...]]):
    pass


@dataclass(frozen=True, slots=True)
class GetCapabilities(Query[tuple[dict[str, object], ...]]):
    pass
