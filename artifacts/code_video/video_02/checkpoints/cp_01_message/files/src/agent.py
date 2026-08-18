"""
Agentic Studio — Message Representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VALID_ROLES = ("system", "user", "assistant")
RoleType = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    """Immutable representation of a conversation turn."""

    role: RoleType
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"Invalid role '{self.role}'. Allowed roles: {VALID_ROLES}"
            )
        if not isinstance(self.content, str):
            raise TypeError("Message content must be a string")
