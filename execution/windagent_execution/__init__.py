"""
Execution Package for WindAgent Architecture V2.
Re-exports execution runtime adapters.
"""

from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter
from windagent_execution.adapters.hermes_runtime_adapter import HermesRuntimeAdapter

__all__ = [
    "FakeRuntimeAdapter",
    "HermesRuntimeAdapter",
]
