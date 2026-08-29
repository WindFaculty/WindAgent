"""
Memory Write Policy & Security Validator for WindAgent Memory Package.
Enforces secret masking, provenance requirements, scope isolation, and reusability checks before writes.
"""

from __future__ import annotations
import logging
import re
from typing import Union

from windagent_core.errors.exceptions import ValidationError, PermissionDeniedError
from windagent_core.domain.memory_v2 import (
    MemoryRecordV2,
    MemoryScope,
    VALIDATED_STATUSES,
    ValidationStatus,
)
from windagent_memory.models import MemoryRecord

logger = logging.getLogger("windagent.memory.write_policy")

SECRET_REGEX_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"ghp_[a-zA-Z0-9]{30,}",
    r"password\s*=\s*['\"][^'\"]+['\"]",
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
]


class MemoryWritePolicy:
    def __init__(
        self,
        enforce_provenance: bool = True,
        min_promotion_confidence: float = 0.5,
        min_promotion_sample_size: int = 1,
    ):
        self.enforce_provenance = enforce_provenance
        self.min_promotion_confidence = min_promotion_confidence
        self.min_promotion_sample_size = min_promotion_sample_size

    def contains_secrets(self, text: str) -> bool:
        for pat in SECRET_REGEX_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE):
                return True
        return False

    def validate_and_enforce(self, record: Union[MemoryRecord, MemoryRecordV2]) -> None:
        """Validates memory write request. Raises ValidationError/PermissionDeniedError if non-compliant."""
        val_str = str(record.value)

        # 1. Secret Exclusion Check
        if self.contains_secrets(val_str) or self.contains_secrets(str(record.key)):
            logger.warning(f"Memory write denied for key [{record.key}]: Value contains detected secret credentials.")
            raise PermissionDeniedError(
                message="Memory write denied: Storing API keys, tokens, or passwords in persistent memory is forbidden.",
                code="WINDAGENT_ERR_MEMORY_SECRET_FORBIDDEN",
                details={"key": record.key, "scope": getattr(record.scope, "value", str(record.scope))},
            )

        # 2. Provenance Requirement Check
        if self.enforce_provenance and not record.provenance_source:
            raise ValidationError(f"Memory write for key [{record.key}] rejected: Missing mandatory provenance_source.")

        # 3. Scope Isolation Check
        if record.scope == MemoryScope.PROJECT and not record.project_id:
            raise ValidationError(f"Project scope memory write for key [{record.key}] requires a valid project_id.")

        if record.scope == MemoryScope.SESSION and not record.session_id:
            raise ValidationError(f"Session scope memory write for key [{record.key}] requires a valid session_id.")

        # 4. Learning Admission Gate (Phase 6 §11)
        learning_meta = getattr(record, "learning_metadata", None)
        if learning_meta is not None:
            # Check confidence bounds
            conf = getattr(learning_meta, "confidence", 0.0)
            if not (0.0 <= conf <= 1.0):
                raise ValidationError(f"Invalid confidence score {conf}: must be between 0.0 and 1.0.")

            # Check sample size
            sample_size = getattr(learning_meta, "sample_size", 0)
            if sample_size < 0:
                raise ValidationError(f"Invalid sample_size {sample_size}: cannot be negative.")

            # Strict check for PROMOTED or VALIDATED policy memories
            val_status = getattr(learning_meta, "validation_status", ValidationStatus.UNVALIDATED)
            if isinstance(val_status, str):
                try:
                    val_status = ValidationStatus(val_status)
                except ValueError:
                    pass

            if record.scope == MemoryScope.POLICY and val_status in VALIDATED_STATUSES:
                if conf < self.min_promotion_confidence:
                    raise ValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted: "
                        f"confidence {conf} < threshold {self.min_promotion_confidence}."
                    )
                if sample_size < self.min_promotion_sample_size:
                    raise ValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted: "
                        f"sample size {sample_size} < threshold {self.min_promotion_sample_size}."
                    )
                evidence_refs = getattr(learning_meta, "evidence_refs", [])
                source_run_ids = getattr(learning_meta, "source_run_ids", [])
                if not evidence_refs and not source_run_ids:
                    raise ValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted without evidence_refs or source_run_ids."
                    )

        logger.debug(f"Memory write policy approved record [{record.key}] under scope [{getattr(record.scope, 'value', str(record.scope))}]")
