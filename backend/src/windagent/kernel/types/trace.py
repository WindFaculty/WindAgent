"""Pure W3C trace identifier validation primitives."""

from __future__ import annotations

import re

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def validate_trace_id(value: str) -> str:
    """Normalize and validate a non-zero 128-bit trace identifier."""
    return _validated_hex(value, _TRACE_ID_RE, "trace_id", 32)


def validate_span_id(value: str) -> str:
    """Normalize and validate a non-zero 64-bit span identifier."""
    return _validated_hex(value, _SPAN_ID_RE, "span_id", 16)


def _validated_hex(value: str, pattern: re.Pattern[str], name: str, size: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    candidate = value.strip().lower()
    if not pattern.fullmatch(candidate) or candidate == "0" * size:
        raise ValueError(f"{name} must be a non-zero {size}-character hexadecimal value")
    return candidate
