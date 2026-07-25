"""
V2 Canonical Schema Migrations for WindAgent Storage Layer.

Migrations from legacy backend schema to canonical V2 schema.
"""

from windagent_storage.migrations.v2_canonical.migration_001_initial import (
    upgrade as upgrade_001,
    downgrade as downgrade_001,
)
from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import (
    upgrade as upgrade_002,
    downgrade as downgrade_002,
)

__all__ = [
    "upgrade_001",
    "downgrade_001",
    "upgrade_002",
    "downgrade_002",
]
