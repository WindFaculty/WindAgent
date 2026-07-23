"""
Memory Models & Scopes for WindAgent Memory Package.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class MemoryScope(str, Enum):
    SESSION = "session"
    PROJECT = "project"
    USER = "user"
    EPISODIC = "episodic"


@dataclass
class MemoryRecord:
    id: str
    scope: MemoryScope
    key: str
    value: Any
    provenance_source: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope.value,
            "key": self.key,
            "value": self.value,
            "provenance_source": self.provenance_source,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
