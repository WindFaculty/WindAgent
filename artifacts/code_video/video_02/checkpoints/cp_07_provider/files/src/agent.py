"""
Agentic Studio (v0.1) — Simple Agent Core.

Domain Architecture:
User ──> Agent ──> LLMClient ──> Answer

Infrastructure:
OpenAICompatibleProvider Adapter (API key loaded from environment)
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import List, Literal, Optional, Protocol, runtime_checkable
import urllib.error
import urllib.request

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


class Agent:
    """A minimal, modular AI Agent without vendor SDK dependencies."""

    def __init__(self, config: AgentConfig, llm_client: LLMClient) -> None:
        self.config = config
        self.llm_client = llm_client

    def run(self, user_input: str) -> str:
        """
        Process user input:
        user_input -> system Message -> user Message -> LLMClient.generate() -> answer
        """
        messages: List[Message] = []
        if self.config.system_prompt:
            messages.append(Message(role="system", content=self.config.system_prompt))
        messages.append(Message(role="user", content=user_input))

        return self.llm_client.generate(messages)


class OpenAICompatibleProvider:
    """
    Infrastructure adapter implementing LLMClient.
    Uses standard library HTTP without external vendor SDKs.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
    ) -> None:
        self.api_key = api_key or os.getenv("PROVIDER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

    def generate(self, messages: List[Message]) -> str:
        if not self.api_key:
            raise ValueError(
                "API key not found. Set PROVIDER_API_KEY or OPENAI_API_KEY in environment."
            )

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as err:
            raise RuntimeError(f"Provider request failed: {err}") from err


if __name__ == "__main__":
    # Cold open demo execution
    config = AgentConfig(
        name="SimpleAgent",
        system_prompt="You are an AI assistant in Agentic Studio v0.1.",
    )
    fake_client = FakeLLMClient(
        default_response="Hello! I am your simple AI Agent running on Agentic Studio v0.1."
    )
    agent = Agent(config=config, llm_client=fake_client)
    user_query = "Hello, what can you do?"
    answer = agent.run(user_query)
    print(f"User: {user_query}")
    print(f"Agent: {answer}")
