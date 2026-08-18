"""
Agentic Studio — Message & AgentConfig.
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


@dataclass(frozen=True)
class AgentConfig:
    """Configuration settings for an Agent instance."""

    name: str
    system_prompt: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.7

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("AgentConfig name cannot be empty")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(
                f"Temperature must be between 0.0 and 2.0, got {self.temperature}"
            )
