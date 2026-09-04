"""Tool result domain (Phase 12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Canonical result of one tool execution."""

    call_id: str
    success: bool
    data: Any | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id.strip():
            raise ValueError("call_id cannot be empty")
        if not isinstance(self.success, bool):
            raise TypeError("success must be a bool")
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError("error must be a string or None")
        if isinstance(self.execution_time_ms, bool) or not isinstance(
            self.execution_time_ms, (int, float)
        ):
            raise TypeError("execution_time_ms must be a number")
        if self.execution_time_ms < 0:
            raise ValueError("execution_time_ms cannot be negative")
        object.__setattr__(self, "execution_time_ms", float(self.execution_time_ms))
        if not isinstance(self.completed_at, datetime):
            raise TypeError("completed_at must be a datetime")

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "completed_at": self.completed_at.isoformat(),
        }

    @property
    def is_failure(self) -> bool:
        return not self.success


__all__ = ["ToolResult"]
