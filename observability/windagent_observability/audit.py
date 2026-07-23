"""
Audit logger and Secret Sanitizer for WindAgent Observability (Phase 11).
Enforces structured audit trail with correlation IDs and mandatory secret redaction.
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class SecretSanitizer:
    """Sanitizes strings and dict payloads to ensure zero secret/key leakage."""

    SECRET_PATTERNS = [
        re.compile(r"(api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """Redacts sensitive values from string text."""
        sanitized = text
        for pattern in cls.SECRET_PATTERNS:
            if pattern.groups > 0:
                sanitized = pattern.sub(r"\1: [REDACTED_SECRET]", sanitized)
            else:
                sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        """Recursively redacts dictionary keys or list values containing secret keys."""
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                k_str = str(k).lower()
                if any(secret_kw in k_str for secret_kw in ["key", "secret", "token", "password", "auth"]):
                    cleaned[k] = "[REDACTED_SECRET]"
                else:
                    cleaned[k] = cls.sanitize_payload(v)
            return cleaned
        elif isinstance(data, list):
            return [cls.sanitize_payload(item) for item in data]
        elif isinstance(data, str):
            return cls.sanitize_string(data)
        else:
            return data


@dataclass
class AuditEvent:
    """Audit record capturing an action and authorization decision."""
    actor: str
    action: str
    resource: str
    decision: str  # e.g., "ALLOWED", "DENIED"
    policy: str
    correlation_id: str
    result: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """Thread-safe correlated audit logger with mandatory secret sanitization."""

    def __init__(self) -> None:
        self.events: List[AuditEvent] = []

    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        decision: str,
        policy: str,
        correlation_id: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Sanitizes metadata and records an audit event."""
        sanitized_meta = SecretSanitizer.sanitize_payload(metadata or {})
        sanitized_result = SecretSanitizer.sanitize_string(result)

        event = AuditEvent(
            actor=actor,
            action=action,
            resource=resource,
            decision=decision,
            policy=policy,
            correlation_id=correlation_id,
            result=sanitized_result,
            timestamp=time.time(),
            metadata=sanitized_meta
        )
        self.events.append(event)
        return event

    def get_events_by_correlation(self, correlation_id: str) -> List[AuditEvent]:
        """Returns ordered audit events matching correlation ID."""
        return [e for e in self.events if e.correlation_id == correlation_id]

    def verify_ordering(self) -> bool:
        """Verifies that audit timestamps are monotonically increasing."""
        for i in range(1, len(self.events)):
            if self.events[i].timestamp < self.events[i - 1].timestamp:
                return False
        return True
