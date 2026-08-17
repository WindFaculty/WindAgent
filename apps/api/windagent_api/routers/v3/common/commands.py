"""
Canonical Command Receipt for Asynchronous Actions in Unified API V3.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class CommandReceipt(BaseModel):
    """
    Standard HTTP 202 Accepted payload returned when an asynchronous workflow or action is scheduled.
    """
    command_id: str = Field(..., description="Unique command tracking identifier")
    status: str = Field(default="ACCEPTED", description="Command acceptance status ('ACCEPTED', 'QUEUED')")
    resource_id: Optional[str] = Field(
        default=None,
        description="Target resource identifier affected by the command"
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Correlation ID associated with command execution"
    )
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO 8601 UTC submission timestamp"
    )
