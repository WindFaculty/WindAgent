"""Persistence contracts and the concrete SQL transaction boundary.

``contracts.py`` stays infrastructure-free (architecture gate).  The
adapter modules — engine management, transaction primitives, the SQL unit
of work, health probes, shared metadata and PostgreSQL helpers — live
alongside it and are the only place where the persistence toolchain is
imported (plan section 8 target layout).
"""

from .contracts import UnitOfWork
from .database import Database, NonCanonicalDatabaseError
from .health import (
    DatabaseHealthReport,
    check_database_health,
    wait_for_database,
)
from .metadata import NAMING_CONVENTION, metadata, target_metadata
from .transaction import (
    IsolationLevel,
    TransactionOutcome,
    TransactionScope,
    TransactionScopeError,
)
from .unit_of_work import (
    CHECKPOINT_BEFORE_COMMIT,
    CHECKPOINT_BEFORE_ROLLBACK,
    CheckpointHook,
    RepositoryFactory,
    SqlUnitOfWork,
    UnitOfWorkNotActiveError,
    UnitOfWorkStateError,
)

__all__ = [
    "CHECKPOINT_BEFORE_COMMIT",
    "CHECKPOINT_BEFORE_ROLLBACK",
    "CheckpointHook",
    "Database",
    "DatabaseHealthReport",
    "IsolationLevel",
    "NAMING_CONVENTION",
    "NonCanonicalDatabaseError",
    "RepositoryFactory",
    "SqlUnitOfWork",
    "TransactionOutcome",
    "TransactionScope",
    "TransactionScopeError",
    "UnitOfWork",
    "UnitOfWorkNotActiveError",
    "UnitOfWorkStateError",
    "check_database_health",
    "metadata",
    "target_metadata",
    "wait_for_database",
]
