"""Compatibility shim — re-exports from tests.fakes.providers.provider_graph.

Deprecated: import from tests.fakes.providers.provider_graph instead.
"""

from tests.fakes.providers.provider_graph import (  # noqa: F401
    PersistentRouteLocks,
    seed_canonical_model,
    seed_provider_graph,
)

__all__ = ["PersistentRouteLocks", "seed_canonical_model", "seed_provider_graph"]
