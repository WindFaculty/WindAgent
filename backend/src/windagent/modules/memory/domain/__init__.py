"""Domain layer of the Memory bounded context."""

from .errors import (
    MemoryConflictError,
    MemoryError,
    MemoryNotFoundError,
    MemoryPermissionDeniedError,
    MemoryStaleVersionError,
    MemoryValidationError,
)
from .models import (
    LearningMetadata,
    MemoryRecord,
    RetentionPolicy,
    compute_content_hash,
)
from .policy import (
    SECRET_REGEX_PATTERNS,
    MemoryWritePolicy,
)
from .scope import (
    DEFAULT_SCOPE_TTL,
    TERMINAL_VALIDATION_STATUSES,
    VALIDATED_STATUSES,
    MemoryScope,
    ValidationStatus,
)

__all__ = [
    "DEFAULT_SCOPE_TTL",
    "LearningMetadata",
    "MemoryConflictError",
    "MemoryError",
    "MemoryNotFoundError",
    "MemoryPermissionDeniedError",
    "MemoryRecord",
    "MemoryScope",
    "MemoryStaleVersionError",
    "MemoryValidationError",
    "MemoryWritePolicy",
    "RetentionPolicy",
    "SECRET_REGEX_PATTERNS",
    "TERMINAL_VALIDATION_STATUSES",
    "VALIDATED_STATUSES",
    "ValidationStatus",
    "compute_content_hash",
]
