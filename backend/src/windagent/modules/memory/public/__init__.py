"""Public surface of the Memory bounded context."""

from __future__ import annotations

from ..api.routes import MODULE_ID, MODULE_VERSION, PREFIX, create_memory_router
from ..application.models import MemoryRecordView, MemoryStatsView
from ..application.runtime import (
    MemoryServices,
    bind_services,
    current_services,
    resolve_services,
)
from ..domain.errors import (
    MemoryConflictError,
    MemoryError,
    MemoryNotFoundError,
    MemoryPermissionDeniedError,
    MemoryStaleVersionError,
    MemoryValidationError,
)
from ..domain.models import (
    LearningMetadata,
    MemoryRecord,
    RetentionPolicy,
    compute_content_hash,
)
from ..domain.policy import (
    SECRET_REGEX_PATTERNS,
    MemoryWritePolicy,
)
from ..domain.scope import (
    DEFAULT_SCOPE_TTL,
    TERMINAL_VALIDATION_STATUSES,
    VALIDATED_STATUSES,
    MemoryScope,
    ValidationStatus,
)
from ..infrastructure.memory import (
    InMemoryMemoryStore,
    memory_scope_factory,
)
from ..infrastructure.repository import (
    SqlMemoryStore,
    sql_scope_factory,
)
from ..manifest import (
    MEMORY_JOB_TYPES,
    build_memory_manifest,
    manifest,
)

__all__ = [
    "DEFAULT_SCOPE_TTL",
    "InMemoryMemoryStore",
    "LearningMetadata",
    "MEMORY_JOB_TYPES",
    "MODULE_ID",
    "MODULE_VERSION",
    "MemoryConflictError",
    "MemoryError",
    "MemoryNotFoundError",
    "MemoryPermissionDeniedError",
    "MemoryRecord",
    "MemoryRecordView",
    "MemoryScope",
    "MemoryServices",
    "MemoryStaleVersionError",
    "MemoryStatsView",
    "MemoryValidationError",
    "MemoryWritePolicy",
    "PREFIX",
    "RetentionPolicy",
    "SECRET_REGEX_PATTERNS",
    "SqlMemoryStore",
    "TERMINAL_VALIDATION_STATUSES",
    "VALIDATED_STATUSES",
    "ValidationStatus",
    "bind_services",
    "build_memory_manifest",
    "compute_content_hash",
    "create_memory_router",
    "current_services",
    "manifest",
    "memory_scope_factory",
    "resolve_services",
    "sql_scope_factory",
]
