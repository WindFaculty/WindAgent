"""Compatibility shim — re-exports from tests.fakes.providers.routing.

Deprecated: import from tests.fakes.providers.routing instead.
"""

from tests.fakes.providers.routing import InMemoryBindingStore, InMemoryLockStore  # noqa: F401

__all__ = ["InMemoryBindingStore", "InMemoryLockStore"]
