"""Canonical Tool Result model for WindAgent Core contracts (Phase 5)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from windagent_core.domain.types import ToolCallId


@dataclass(frozen=True)
class ToolResult:
    """Canonical model for tool execution results."""

    call_id: ToolCallId
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
