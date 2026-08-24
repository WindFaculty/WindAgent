"""Compatibility shim — re-exports from tests.fakes.execution.task_queue.

Deprecated: import from tests.fakes.execution.task_queue instead.
"""

from tests.fakes.execution.task_queue import FakeDurableTaskQueue  # noqa: F401

__all__ = ["FakeDurableTaskQueue"]
