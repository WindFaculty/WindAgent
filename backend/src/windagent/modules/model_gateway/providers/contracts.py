"""Provider protocol contracts: normalized requests, responses, and streams.

EXTRACT_LOGIC of the frozen ``core/windagent_core/contracts/providers``
request/response/usage/stream shapes.  These DTOs are transport-neutral and
provider-agnostic; every adapter maps them to and from its wire protocol.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class FinishReason(StrEnum):
    """Why the provider stopped generating."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class StreamEventType(StrEnum):
    """The kind of one normalized streaming event."""

    TOKEN = "token"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    METADATA = "metadata"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Token accounting for one completion (auto-summing total)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float | None = None

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    """One tool invocation requested by the model."""

    id: str | None
    name: str
    arguments: str = ""


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One conversation message in normalized form."""

    role: str
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ImagePart:
    """One inline image attachment (base64 media plus MIME type)."""

    mime_type: str
    data: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """A normalized completion request handed to exactly one adapter."""

    model_id: str
    messages: tuple[ProviderMessage, ...] = ()
    prompt: str = ""
    system_instruction: str | None = None
    temperature: float | None = 0.7
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    tool_choice: str | Mapping[str, Any] | None = None
    structured_output_schema: Mapping[str, Any] | None = None
    image_parts: tuple[ImagePart, ...] = ()
    provider_extensions: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    @property
    def output_limit(self) -> int | None:
        """The effective output token limit (new field wins over legacy)."""
        if self.max_output_tokens is not None:
            return self.max_output_tokens
        return self.max_tokens


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """A normalized completion result from one provider attempt."""

    provider_model_id: str
    text: str | None = None
    tool_calls: tuple[ProviderToolCall, ...] = ()
    structured_output: object = None
    finish_reason: str = FinishReason.STOP.value
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider_request_id: str | None = None
    first_token_latency_ms: float | None = None
    total_latency_ms: float = 0.0
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderStreamEvent:
    """One normalized streaming chunk; ``done`` carries final usage."""

    event_type: StreamEventType
    sequence_number: int = 0
    delta: str | None = None
    reasoning_delta: str | None = None
    tool_call_delta: ProviderToolCall | None = None
    finish_reason: str | None = None
    usage: ProviderUsage | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    """One model reported by a provider discovery listing."""

    id: str
    context_window: int | None = None
    raw_pricing: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealthReport:
    """The outcome of one provider health probe."""

    provider_name: str
    healthy: bool
    latency_ms: float = 0.0
    status_code: int | None = None
    error_message: str | None = None
    last_check_at: datetime | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    """The structural protocol every provider transport implements."""

    provider_name: str

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        """Execute one completion call."""

    def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Execute one streaming completion call."""

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        """Discover the models the endpoint currently exposes."""

    async def health(self) -> HealthReport:
        """Probe endpoint health (discovery-based in the old system)."""


def messages_from_prompt(prompt: str) -> tuple[ProviderMessage, ...]:
    """Convenience for single-turn requests."""
    return (ProviderMessage(role="user", content=prompt),)


def tool_maps(tools: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """Freeze a tool definition sequence for a request."""
    return tuple(tools)
