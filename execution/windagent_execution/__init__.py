"""
Execution Package for WindAgent Architecture V2 (Phase 18).
Re-exports execution runtime registry, adapters, requests, results, cancellation, sandbox, and worktree.
"""

from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_execution.requests import DurableExecutionRequest
from windagent_execution.results import ExecutionResultHandler, FencingValidatedResult
from windagent_execution.cancellation import CancellationBroadcaster
from windagent_execution.streaming import ExecutionStreamManager, StreamChunk
from windagent_execution.sandbox.isolation import ExecutionSandbox, SandboxConfig
from windagent_execution.worktree.context import WorktreeContextManager

from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter
from windagent_execution.adapters.hermes_runtime_adapter import HermesRuntimeAdapter
from windagent_execution.adapters.tool_runtime import ToolRuntimeAdapter
from windagent_execution.adapters.browser_runtime import BrowserRuntimeAdapter
from windagent_execution.adapters.local_agent import LocalAgentRuntimeAdapter
from windagent_execution.adapters.subprocess_runtime import SubprocessRuntimeAdapter

__version__ = "0.2.0"

__all__ = [
    "ExecutionRuntimeRegistry",
    "DurableExecutionRequest",
    "ExecutionResultHandler",
    "FencingValidatedResult",
    "CancellationBroadcaster",
    "ExecutionStreamManager",
    "StreamChunk",
    "ExecutionSandbox",
    "SandboxConfig",
    "WorktreeContextManager",
    "FakeRuntimeAdapter",
    "HermesRuntimeAdapter",
    "ToolRuntimeAdapter",
    "BrowserRuntimeAdapter",
    "LocalAgentRuntimeAdapter",
    "SubprocessRuntimeAdapter",
]
