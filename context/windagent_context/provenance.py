"""
Context Provenance Metadata & Models for WindAgent Context Package.
Tracks source, file location, retrieval rationale, token cost, freshness, and access rights.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class ContextItemProvenance:
    source: str
    retrieval_reason: str
    token_cost: int
    file_path: Optional[str] = None
    line_range: Optional[str] = None
    freshness: float = 1.0  # 1.0 = newest/fresh, 0.0 = stale
    confidence: float = 1.0
    access_permission: str = "read"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "retrieval_reason": self.retrieval_reason,
            "token_cost": self.token_cost,
            "file_path": self.file_path,
            "line_range": self.line_range,
            "freshness": self.freshness,
            "confidence": self.confidence,
            "access_permission": self.access_permission,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ContextItem:
    item_id: str
    content: str
    provenance: ContextItemProvenance
