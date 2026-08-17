"""
Canonical Resource Base Models for Unified API V3.
"""

from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ResourceBase(BaseModel):
    """
    Standard base fields required for all top-level V3 resources.
    """
    id: str = Field(..., description="Unique entity identifier with canonical type prefix")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO 8601 UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO 8601 UTC last-modified timestamp"
    )
    version: int = Field(
        default=1,
        description="Monotonically increasing integer for optimistic concurrency control"
    )
