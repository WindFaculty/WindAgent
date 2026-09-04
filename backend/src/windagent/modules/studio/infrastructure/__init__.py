"""Infrastructure layer of Studio — SQL + in-memory adapters."""

from .memory import InMemoryStudioStore, InMemoryTransactionScope, memory_scope_factory
from .repository import SqlStudioStore, SqlTransactionScope, make_store, sql_scope_factory
from .tables import (
    artifacts_table,
    characters_table,
    episodes_table,
    projects_table,
    revisions_table,
    series_table,
    storyboards_table,
    world_locations_table,
    world_props_table,
)

__all__ = [
    "InMemoryStudioStore",
    "InMemoryTransactionScope",
    "SqlStudioStore",
    "SqlTransactionScope",
    "artifacts_table",
    "characters_table",
    "episodes_table",
    "make_store",
    "memory_scope_factory",
    "projects_table",
    "revisions_table",
    "series_table",
    "sql_scope_factory",
    "storyboards_table",
    "world_locations_table",
    "world_props_table",
]
