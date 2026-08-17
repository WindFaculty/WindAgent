"""
Canonical Cursor Pagination for Unified API V3.
"""

from __future__ import annotations
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageInfo(BaseModel):
    """
    Metadata describing the current cursor position and forward availability.
    """
    next_cursor: Optional[str] = Field(
        default=None,
        description="Opaque token to fetch the subsequent page of results"
    )
    has_more: bool = Field(
        default=False,
        description="True if there are additional items following this page"
    )
    total_count: Optional[int] = Field(
        default=None,
        description="Optional total count of items across all pages if known"
    )


class CursorPage(BaseModel, Generic[T]):
    """
    Uniform envelope for all paginated collection responses in V3.
    """
    items: List[T] = Field(..., description="Array of entities on the current page")
    page_info: PageInfo = Field(..., description="Cursor navigation indicators")
