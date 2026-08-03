"""
Migration Registry for WindAgent Storage Layer.
Manages all migrations, their order, and execution.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging

from sqlalchemy import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger("windagent.storage.migrations")


class MigrationDirection(Enum):
    """Direction of migration."""
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"


class MigrationStatus(Enum):
    """Status of a migration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationRecord:
    """Record of a migration execution."""
    revision: str
    name: str
    direction: MigrationDirection
    status: MigrationStatus
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    checksum: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision": self.revision,
            "name": self.name,
            "direction": self.direction.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "checksum": self.checksum,
        }


@dataclass
class MigrationSpec:
    """Specification for a migration."""
    revision: str
    name: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Ensure revision is a valid identifier
        if not self.revision or len(self.revision) > 64:
            raise ValueError(f"Invalid revision: {self.revision}")


class MigrationRegistry:
    """
    Registry of all database migrations.
    
    Manages migration order, dependencies, and execution tracking.
    Each migration must have:
    - A unique revision identifier
    - Upgrade function (source schema -> target schema)
    - Downgrade function (target schema -> source schema)
    - Schema checksum for verification
    """
    
    def __init__(self) -> None:
        self._migrations: Dict[str, MigrationSpec] = {}
        self._upgrade_functions: Dict[str, Callable[[Session], None]] = {}
        self._downgrade_functions: Dict[str, Callable[[Session], None]] = {}
        self._migration_order: List[str] = []
    
    def register(
        self,
        revision: str,
        name: str,
        description: str,
        upgrade: Callable[[Session], None],
        downgrade: Callable[[Session], None],
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """
        Register a new migration.
        
        Args:
            revision: Unique revision identifier (e.g., "001", "002_initial_schema")
            name: Human-readable name
            description: Detailed description
            upgrade: Function to upgrade the schema
            downgrade: Function to downgrade the schema
            dependencies: List of revision dependencies
        """
        if revision in self._migrations:
            raise ValueError(f"Migration {revision} already registered")
        
        spec = MigrationSpec(
            revision=revision,
            name=name,
            description=description,
            dependencies=dependencies or [],
        )
        self._migrations[revision] = spec
        self._upgrade_functions[revision] = upgrade
        self._downgrade_functions[revision] = downgrade
        
        # Rebuild migration order (topological sort)
        self._rebuild_order()
        
        logger.info(f"Registered migration {revision}: {name}")
    
    def _rebuild_order(self) -> None:
        """Rebuild migration order based on dependencies (topological sort)."""
        # Simple topological sort (Kahn's algorithm)
        in_degree: Dict[str, int] = {r: 0 for r in self._migrations}
        graph: Dict[str, List[str]] = {r: [] for r in self._migrations}
        
        for revision, spec in self._migrations.items():
            for dep in spec.dependencies:
                if dep not in self._migrations:
                    raise ValueError(f"Dependency {dep} not found for migration {revision}")
                graph[dep].append(revision)
                in_degree[revision] += 1
        
        # Kahn's algorithm
        queue = [r for r in in_degree if in_degree[r] == 0]
        self._migration_order = []
        
        while queue:
            node = queue.pop(0)
            self._migration_order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(self._migration_order) != len(self._migrations):
            raise ValueError("Circular dependency detected in migrations")
    
    def get_migration_order(self) -> List[str]:
        """Get migrations in execution order."""
        return self._migration_order.copy()
    
    def get_migration(self, revision: str) -> MigrationSpec:
        """Get migration specification by revision."""
        if revision not in self._migrations:
            raise ValueError(f"Migration {revision} not found")
        return self._migrations[revision]
    
    def get_upgrade_function(self, revision: str) -> Callable[[Session], None]:
        """Get upgrade function for a migration."""
        if revision not in self._upgrade_functions:
            raise ValueError(f"Upgrade function for {revision} not found")
        return self._upgrade_functions[revision]
    
    def get_downgrade_function(self, revision: str) -> Callable[[Session], None]:
        """Get downgrade function for a migration."""
        if revision not in self._downgrade_functions:
            raise ValueError(f"Downgrade function for {revision} not found")
        return self._downgrade_functions[revision]
    
    def get_all_revisions(self) -> List[str]:
        """Get all registered migration revisions."""
        return list(self._migrations.keys())
    
    def get_applied_migrations(self, engine: Engine) -> List[MigrationRecord]:
        """Get list of applied migrations from the database."""
        # This will be implemented to query the migration history table
        # For now, return empty list
        return []
    
    def get_pending_migrations(self, engine: Engine) -> List[str]:
        """Get list of pending migrations."""
        applied = self.get_applied_migrations(engine)
        applied_revisions = {r.revision for r in applied}
        return [r for r in self._migration_order if r not in applied_revisions]


# Global registry instance
migration_registry = MigrationRegistry()


def _register_builtin_migrations() -> None:
    from windagent_storage.migrations.v2_canonical import (
        migration_001_initial,
        migration_002_legacy_data,
    )

    migration_registry.register(
        revision=migration_001_initial.MIGRATION_REVISION,
        name=migration_001_initial.MIGRATION_NAME,
        description=migration_001_initial.MIGRATION_DESCRIPTION,
        upgrade=migration_001_initial.upgrade,
        downgrade=migration_001_initial.downgrade,
    )
    migration_registry.register(
        revision=migration_002_legacy_data.MIGRATION_REVISION,
        name=migration_002_legacy_data.MIGRATION_NAME,
        description=migration_002_legacy_data.MIGRATION_DESCRIPTION,
        upgrade=migration_002_legacy_data.upgrade,
        downgrade=migration_002_legacy_data.downgrade,
        dependencies=[migration_001_initial.MIGRATION_REVISION],
    )


_register_builtin_migrations()
