"""Explicit execution infrastructure factory (Architecture V3 Phase B hardening).

This module is the SINGLE allowlisted construction point for concrete
execution runtime adapters inside the execution package:

    composition root / factory  ->  concrete adapter  ->  core port

The runtime registry builds its default capability map through these creators
instead of hard-instantiating adapter classes inline.
"""

from __future__ import annotations

from windagent_execution.adapters.browser_runtime import BrowserRuntimeAdapter
from windagent_execution.adapters.local_agent import LocalAgentRuntimeAdapter
from windagent_execution.adapters.subprocess_runtime import SubprocessRuntimeAdapter
from windagent_execution.adapters.tool_runtime import ToolRuntimeAdapter


def create_tool_runtime_adapter(*, allow_simulation: bool = False) -> ToolRuntimeAdapter:
    return ToolRuntimeAdapter(allow_simulation=allow_simulation)


def create_browser_runtime_adapter() -> BrowserRuntimeAdapter:
    return BrowserRuntimeAdapter()


def create_local_agent_runtime_adapter() -> LocalAgentRuntimeAdapter:
    return LocalAgentRuntimeAdapter()


def create_subprocess_runtime_adapter() -> SubprocessRuntimeAdapter:
    return SubprocessRuntimeAdapter()


__all__ = [
    "create_browser_runtime_adapter",
    "create_local_agent_runtime_adapter",
    "create_subprocess_runtime_adapter",
    "create_tool_runtime_adapter",
]
