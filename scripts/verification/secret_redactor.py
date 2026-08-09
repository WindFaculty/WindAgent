"""
Secret and Local Path Redactor for Stage H test evidence.

Ensures test artifacts, log outputs, trace files, and evidence bundles
contain zero sensitive tokens, environment secrets, or explicit user path leaks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Union

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{32,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"([a-zA-Z]:\\[^\s\"'\(\)]+)", re.IGNORECASE), "[REDACTED_PATH]"),
    (re.compile(r"(/home/[^\s\"'\(\)]+|/Users/[^\s\"'\(\)]+)", re.IGNORECASE), "[REDACTED_PATH]"),
]


def sanitize_text(text: str) -> str:
    """Sanitize secrets and file system paths from raw text output."""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_structure(data: Union[Dict[str, Any], List[str], str]) -> Any:
    """Recursively redact dictionary or list elements."""
    if isinstance(data, str):
        return sanitize_text(data)
    elif isinstance(data, list):
        return [sanitize_structure(item) for item in data]
    elif isinstance(data, dict):
        return {key: sanitize_structure(val) for key, val in data.items()}
    return data
