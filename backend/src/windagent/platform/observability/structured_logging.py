"""Structured JSON logging with causal context and secret redaction."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from .context import current_operation_context

_SENSITIVE_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
)
_HANDLER_MARKER = "_windagent_json_handler"


def redact(value: object, *, key: str | None = None) -> object:
    """Recursively redact values whose field names commonly hold credentials."""
    if key is not None and _is_sensitive(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(name): redact(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class JsonLogFormatter(logging.Formatter):
    """Format standard log records as stable single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        service = getattr(record, "windagent_service", None)
        event = getattr(record, "windagent_event", None)
        attributes = getattr(record, "windagent_attributes", None)
        if service:
            payload["service"] = str(service)
        if event:
            payload["event"] = str(event)
        if isinstance(attributes, Mapping):
            payload["attributes"] = redact(attributes)
        context = current_operation_context()
        if context is not None:
            payload.update(context.to_attributes())
        if record.exc_info is not None:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_type"] = exception_type.__name__
        return json.dumps(redact(payload), separators=(",", ":"), sort_keys=True)


def configure_structured_logging(
    *, level: str | int = "INFO", logger_name: str = "windagent"
) -> logging.Logger:
    """Install one idempotent JSON stream handler on a logger hierarchy."""
    logger = logging.getLogger(logger_name)
    numeric_level = _log_level(level)
    logger.setLevel(numeric_level)
    if not any(getattr(handler, _HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def _is_sensitive(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def _log_level(value: str | int) -> int:
    if isinstance(value, bool):
        raise TypeError("log level must be text or an integer")
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise TypeError("log level must be text or an integer")
    numeric = logging.getLevelName(value.strip().upper())
    if not isinstance(numeric, int):
        raise ValueError(f"unknown log level: {value!r}")
    return numeric
