"""
Error Classification Engine for Orchestration V2 Retry Policy.
Enforces strict retryability checks according to ban_ke_hoach.md §11-12.
UNCLASSIFIED STANDARD EXCEPTIONS DO NOT RETRY BY DEFAULT (FAIL-CLOSED).
"""

from __future__ import annotations

import logging

from windagent_core.errors.exceptions import (
    WindAgentError, RetryableError, NonRetryableError
)

logger = logging.getLogger("windagent.orchestration.retry.classifier")


class ErrorClassifier:
    @staticmethod
    def is_retryable(exc: Exception) -> bool:
        """Determines retryability based on explicit error classification.
        Unclassified standard exceptions fail-closed and return False.
        """
        # Explicit NonRetryableError
        if isinstance(exc, NonRetryableError):
            logger.info(f"Error [{type(exc).__name__}] is explicitly non-retryable.")
            return False

        # Explicit RetryableError
        if isinstance(exc, RetryableError):
            logger.info(f"Error [{type(exc).__name__}] is explicitly retryable.")
            return True

        # Base WindAgentError check
        if isinstance(exc, WindAgentError):
            return getattr(exc, "retryable", False)

        # Built-in network/timeout exceptions
        if isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionRefusedError, OSError)):
            logger.info(f"System error [{type(exc).__name__}] classified as retryable network/IO error.")
            return True

        # Requirement 12: Do NOT default retry unclassified standard exceptions!
        logger.warning(f"Unclassified exception [{type(exc).__name__}: {str(exc)}] defaults to NON-RETRYABLE (fail-closed).")
        return False
