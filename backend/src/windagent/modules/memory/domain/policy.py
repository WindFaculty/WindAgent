"""Memory Write Policy & Security Validator for WindAgent Memory module (Phase 14).

Enforces secret masking, mandatory provenance, scope isolation, and learning admission gates.
"""

from __future__ import annotations

import logging
import re

from .errors import MemoryPermissionDeniedError, MemoryValidationError
from .models import MemoryRecord
from .scope import VALIDATED_STATUSES, MemoryScope

logger = logging.getLogger("windagent.memory.domain.policy")

SECRET_REGEX_PATTERNS: tuple[str, ...] = (
    r"sk-[a-zA-Z0-9]{20,}",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"ghp_[a-zA-Z0-9]{30,}",
    r"password\s*=\s*['\"][^'\"]+['\"]",
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
)


class MemoryWritePolicy:
    def __init__(
        self,
        enforce_provenance: bool = True,
        min_promotion_confidence: float = 0.5,
        min_promotion_sample_size: int = 1,
    ) -> None:
        self.enforce_provenance = enforce_provenance
        self.min_promotion_confidence = min_promotion_confidence
        self.min_promotion_sample_size = min_promotion_sample_size

    def contains_secrets(self, text: str) -> bool:
        for pat in SECRET_REGEX_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE):
                return True
        return False

    def validate_and_enforce(self, record: MemoryRecord) -> None:
        """Validates memory write request against security and domain rules."""
        val_str = str(record.value)

        # 1. Secret Exclusion Check
        if self.contains_secrets(val_str) or self.contains_secrets(str(record.key)):
            logger.warning(
                f"Memory write denied for key [{record.key}]: Value contains detected secret credentials."
            )
            raise MemoryPermissionDeniedError(
                "Memory write denied: Storing API keys, tokens, or passwords in persistent memory is forbidden.",
                context={"key": record.key, "scope": record.scope.value},
            )

        # 2. Mandatory Provenance Check
        if self.enforce_provenance and not record.provenance_source:
            raise MemoryValidationError(
                f"Memory write for key [{record.key}] rejected: Missing mandatory provenance_source."
            )

        # 3. Scope Isolation Check
        if record.scope == MemoryScope.PROJECT and not record.project_id:
            raise MemoryValidationError(
                f"Project scope memory write for key [{record.key}] requires a valid project_id."
            )

        if record.scope == MemoryScope.SESSION and not record.session_id:
            raise MemoryValidationError(
                f"Session scope memory write for key [{record.key}] requires a valid session_id."
            )

        # 4. Learning Admission Gate
        learning_meta = record.learning_metadata
        if learning_meta is not None:
            conf = learning_meta.confidence
            if not (0.0 <= conf <= 1.0):
                raise MemoryValidationError(
                    f"Invalid confidence score {conf}: must be between 0.0 and 1.0."
                )

            sample_size = learning_meta.sample_size
            if sample_size < 0:
                raise MemoryValidationError(
                    f"Invalid sample_size {sample_size}: cannot be negative."
                )

            val_status = learning_meta.validation_status
            if record.scope == MemoryScope.POLICY and val_status in VALIDATED_STATUSES:
                if conf < self.min_promotion_confidence:
                    raise MemoryValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted: "
                        f"confidence {conf} < threshold {self.min_promotion_confidence}."
                    )
                if sample_size < self.min_promotion_sample_size:
                    raise MemoryValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted: "
                        f"sample size {sample_size} < threshold {self.min_promotion_sample_size}."
                    )
                if not learning_meta.evidence_refs and not learning_meta.source_run_ids:
                    raise MemoryValidationError(
                        f"Policy memory [{record.key}] cannot be validated/promoted without evidence_refs or source_run_ids."
                    )
