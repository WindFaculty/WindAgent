"""
Secret Redaction and Sanitization Utilities for WindAgent Core Security.
Ensures API keys, bearer tokens, and sensitive query parameters are never written to logs,
exceptions, traces, or metadata payloads.
"""

from __future__ import annotations
import re
from typing import Any, Dict

_SECRET_PATTERNS = [
    re.compile(
        r"(api[_-]?key|secret|token|authorization|password)[\s=:]+['\"]?([a-zA-Z0-9_\-\.]{6,})['\"]?",
        re.IGNORECASE,
    ),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{6,})", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9_-]{8,})"),  # OpenAI/Anthropic style key
    re.compile(r"(nvapi-[a-zA-Z0-9_-]{8,})"),  # NVIDIA style key
    re.compile(r"(gsk_[a-zA-Z0-9_-]{8,})"),  # Groq/OpenRouter key pattern
    re.compile(r"(AIzaSy[a-zA-Z0-9_-]{20,})"),  # Google API key pattern
    re.compile(r"(ghp_[a-zA-Z0-9]{30,})"),  # GitHub personal access token
    re.compile(r"(xai-[a-zA-Z0-9_-]{16,})"),  # xAI API key
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
                return (
                    f"{val[:3]}***[REDACTED]***{val[-3:]}"
                    if len(val) >= 8
                    else "***[REDACTED]***"
                )
            elif len(groups) == 2:
                prefix, val = groups[0], groups[1]
                masked = (
                    f"{val[:3]}***[REDACTED]***{val[-3:]}"
                    if len(val) >= 8
                    else "***[REDACTED]***"
                )
                return f"{prefix}{masked}"
            return "***[REDACTED]***"

        redacted = pattern.sub(_replace_match, redacted)
    return redacted


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts dictionary values with sensitive keys."""
    if not isinstance(data, dict):
        return data

    sanitized: Dict[str, Any] = {}
    sensitive_key_terms = {
        "api_key",
        "apikey",
        "secret",
        "password",
        "authorization",
        "bearer",
        "cred",
        "auth_token",
        "access_token",
        "private_key",
    }
    non_secret_token_terms = {
        "tokens",
        "tokens_per_sec",
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "reasoning_tokens",
    }

    for key, value in data.items():
        key_lower = str(key).lower()

        # Check if key is a known non-secret token metric
        is_secret_key = any(term in key_lower for term in sensitive_key_terms)
        if (
            "token" in key_lower
            and not any(ns in key_lower for ns in non_secret_token_terms)
            and not is_secret_key
        ):
            is_secret_key = True

        if is_secret_key:
            if isinstance(value, str) and value.startswith("enc:v1:"):
                sanitized[key] = "[ENCRYPTED_SECRET]"
            elif isinstance(value, str) and len(value) > 8:
                sanitized[key] = f"{value[:3]}***[REDACTED]***{value[-3:]}"
            else:
                sanitized[key] = "***[REDACTED]***"
        elif isinstance(value, dict):
            sanitized[key] = redact_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                redact_dict(v)
                if isinstance(v, dict)
                else (redact_text(v) if isinstance(v, str) else v)
                for v in value
            ]
        elif isinstance(value, str):
            sanitized[key] = redact_text(value)
        else:
            sanitized[key] = value

    return sanitized


def redact_before_persist(data: Any) -> Any:
    """Canonical pre-persist redaction gate (Phase 1 — G9.4).

    Apply this at **every** write boundary (commands, tool arguments, events,
    audit logs) so secrets are never persisted or emitted raw:

    - ``dict``   -> recursive key-based redaction (``redact_dict``)
    - ``str``    -> pattern-based text redaction (``redact_text``)
    - ``list``   -> per-item redaction
    - other      -> unchanged

    ``redact_text`` is applied to *all* string values inside dicts, so a secret
    embedded in a message body (``Bearer sk-...``, ``api_key=...``) is masked in
    addition to secret-keyed fields.
    """
    if isinstance(data, dict):
        return redact_dict(data)
    if isinstance(data, list):
        return [redact_before_persist(item) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data
