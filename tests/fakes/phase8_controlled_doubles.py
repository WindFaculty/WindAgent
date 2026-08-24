"""Compatibility shim — re-exports from tests.fakes.execution.controlled_runtime.

Deprecated: import from tests.fakes.execution.controlled_runtime instead.
"""

from tests.fakes.execution.controlled_runtime import (  # noqa: F401
    ControlledHermesRuntime,
    ScriptedProviderAdapter,
)

__all__ = ["ControlledHermesRuntime", "ScriptedProviderAdapter"]
