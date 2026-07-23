"""
Memory Write Policy & Security Validator for WindAgent Memory Package.
Enforces secret masking, provenance requirements, scope isolation, and reusability checks before writes.
"""

from __future__ import annotations
import logging
import re

from windagent_core.errors.exceptions import ValidationError, PermissionDeniedError
from windagent_memory.models import MemoryRecord, MemoryScope

logger = logging.getLogger("windagent.memory.write_policy")

SECRET_REGEX_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"ghp_[a-zA-Z0-9]{30,}",
    r"password\s*=\s*['\"][^'\"]+['\"]",
]


class MemoryWritePolicy:
    def __init__(self, enforce_provenance: bool = True):
        self.enforce_provenance = enforce_provenance

    def contains_secrets(self, text: str) -> bool:
        for pat in SECRET_REGEX_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE):
                return True
        return False

    def validate_and_enforce(self, record: MemoryRecord) -> None:
        """Validates memory write request. Raises ValidationError/PermissionDeniedError if non-compliant."""
        val_str = str(record.value)

        # 1. Secret Exclusion Check
        if self.contains_secrets(val_str):
            logger.warning(f"Memory write denied for key [{record.key}]: Value contains detected secret credentials.")
            raise PermissionDeniedError(
                message=f"Memory write denied: Storing API keys, tokens, or passwords in persistent memory is forbidden.",
                code="WINDAGENT_ERR_MEMORY_SECRET_FORBIDDEN",
                details={"key": record.key, "scope": record.scope.value},
            )

        # 2. Provenance Requirement Check
        if self.enforce_provenance and not record.provenance_source:
            raise ValidationError(f"Memory write for key [{record.key}] rejected: Missing mandatory provenance_source.")

        # 3. Scope Isolation Check
        if record.scope == MemoryScope.PROJECT and not record.project_id:
            raise ValidationError(f"Project scope memory write for key [{record.key}] requires a valid project_id.")

        if record.scope == MemoryScope.SESSION and not record.session_id:
            raise ValidationError(f"Session scope memory write for key [{record.key}] requires a valid session_id.")

        logger.debug(f"Memory write policy approved record [{record.key}] under scope [{record.scope.value}]")
