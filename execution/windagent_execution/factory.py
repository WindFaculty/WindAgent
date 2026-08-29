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


def create_stateful_v1_runtime(*, backing_store=None, sandbox=None, stream_manager=None, worktree_manager=None):  # type: ignore[no-untyped-def]
    from windagent_execution.stateful.adapters.v1 import StatefulV1Adapter

    return StatefulV1Adapter(
        backing_store=backing_store,
        sandbox=sandbox,
        stream_manager=stream_manager,
        worktree_manager=worktree_manager,
    )


def create_stateful_persistent_python_runtime(*, backing_store=None, use_ipython: bool = False):  # type: ignore[no-untyped-def]
    from windagent_execution.stateful.adapters.persistent_python import PersistentPythonRuntime

    return PersistentPythonRuntime(backing_store=backing_store, use_ipython=use_ipython)


def create_stateful_wasm_runtime(*, backing_store=None):  # type: ignore[no-untyped-def]
    from windagent_execution.stateful.adapters.wasm import WasmRuntime

    return WasmRuntime(backing_store=backing_store)


def create_stateful_container_runtime(*, backing_store=None, image: str = "python:3.11-slim"):  # type: ignore[no-untyped-def]
    from windagent_execution.stateful.adapters.container import ContainerRuntime

    return ContainerRuntime(backing_store=backing_store, image=image)


def create_stateful_remote_runtime(*, backing_store=None, endpoint=None):  # type: ignore[no-untyped-def]
    from windagent_execution.stateful.adapters.remote import RemoteRuntime

    return RemoteRuntime(backing_store=backing_store, endpoint=endpoint)


def create_stateful_runtime(*, store: dict | None = None, runtime_name: str = "default"):  # type: ignore[no-untyped-def]
    """Core-compatible host-owned stateful runtime (Phase 3)."""
    from windagent_execution.stateful_runtime import InMemoryStatefulRuntime

    return InMemoryStatefulRuntime(store=store, runtime_name=runtime_name)


def create_core_stateful_runtime(*, store: dict | None = None, runtime_name: str = "default"):  # type: ignore[no-untyped-def]
    return create_stateful_runtime(store=store, runtime_name=runtime_name)


__all__ = [
    "create_browser_runtime_adapter",
    "create_local_agent_runtime_adapter",
    "create_subprocess_runtime_adapter",
    "create_tool_runtime_adapter",
    "create_stateful_v1_runtime",
    "create_stateful_persistent_python_runtime",
    "create_stateful_wasm_runtime",
    "create_stateful_container_runtime",
    "create_stateful_remote_runtime",
    "create_stateful_runtime",
    "create_core_stateful_runtime",
]
