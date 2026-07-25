"""Canonical Tool Invocation model for WindAgent Core contracts (Phase 5).

Single canonical definition — previously duplicated between
``windagent_core.tools.models`` (pydantic) and ``windagent_core.domain.models``
(dataclass). The dataclass shape is canonical; tool implementations and the
permission engine consume this contract.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.domain.types import ToolCallId


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ToolInvocation:
    """Canonical model for tool execution requests."""

    id: ToolCallId
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=_default_utc_now)
    timeout_seconds: Optional[float] = 30.0

    def __post_init__(self) -> None:
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("ToolInvocation tool_name cannot be empty.")

    @property
    def arguments(self) -> Dict[str, Any]:
        """Alias for params — keeps a single canonical invocation contract."""
        return self.params
