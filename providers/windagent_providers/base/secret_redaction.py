"""
Secret Redaction and Sanitization Utilities for WindAgent Provider Subsystem.
Ensures API keys, bearer tokens, and sensitive query parameters are never written to logs,
exceptions, traces, or metadata payloads.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Union

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|token|authorization|password)[\s=:]+['\"]?([a-zA-Z0-9_\-\.]{6,})['\"]?", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{6,})", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9_-]{8,})"),  # OpenAI style key
    re.compile(r"(nvapi-[a-zA-Z0-9_-]{8,})"),  # NVIDIA style key
    re.compile(r"(gsk_[a-zA-Z0-9_-]{8,})"),  # Groq/OpenRouter key pattern
    re.compile(r"(AIzaSy[a-zA-Z0-9_-]{20,})"),  # Google API key pattern
]


def redact_text(text: str) -> str:
    """Redacts known key patterns from raw text string."""
    if not text:
        return text
    
    redacted = text
    for pattern in _SECRET_PATTERNS:
        def _replace_match(match: re.Match[str]) -> str:
            groups = match.groups()
            if len(groups) == 1:
                val = groups[0]
                return f"{val[:3]}***[REDACTED]***{val[-3:]}" if len(val) >= 8 else "***[REDACTED]***"
            elif len(groups) == 2:
                prefix, val = groups[0], groups[1]
                masked = f"{val[:3]}***[REDACTED]***{val[-3:]}" if len(val) >= 8 else "***[REDACTED]***"
                return f"{prefix}{masked}"
            return "***[REDACTED]***"

        redacted = pattern.sub(_replace_match, redacted)
    return redacted


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts dictionary values with sensitive keys."""
    if not isinstance(data, dict):
        return data

    sanitized: Dict[str, Any] = {}
    sensitive_key_terms = {"api_key", "apikey", "secret", "token", "password", "authorization", "bearer", "cred"}

    for key, value in data.items():
        key_lower = str(key).lower()
        if any(term in key_lower for term in sensitive_key_terms):
            if isinstance(value, str) and value.startswith("enc:v1:"):
                sanitized[key] = "[ENCRYPTED_SECRET]"
            elif isinstance(value, str) and len(value) > 8:
                sanitized[key] = f"{value[:3]}***[REDACTED]***{value[-3:]}"
            else:
                sanitized[key] = "***[REDACTED]***"
        elif isinstance(value, dict):
            sanitized[key] = redact_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [redact_dict(v) if isinstance(v, dict) else (redact_text(v) if isinstance(v, str) else v) for v in value]
        elif isinstance(value, str):
            sanitized[key] = redact_text(value)
        else:
            sanitized[key] = value

    return sanitized
