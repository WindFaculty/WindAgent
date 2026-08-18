"""
Agentic Studio — Domain Models, Protocol & Offline Fake LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Protocol, runtime_checkable

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


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining domain abstraction for LLM interactions (no vendor SDK)."""

    def generate(self, messages: List[Message]) -> str:
        """Generate response text given a sequence of messages."""
        ...


class FakeLLMClient:
    """Deterministic, offline LLM client for testing and local verification."""

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        default_response: str = "Hello! I am your AI agent.",
    ) -> None:
        self.responses = list(responses) if responses is not None else []
        self.default_response = default_response
        self.call_history: List[List[Message]] = []

    def generate(self, messages: List[Message]) -> str:
        self.call_history.append(list(messages))
        if self.responses:
            return self.responses.pop(0)
        return self.default_response
