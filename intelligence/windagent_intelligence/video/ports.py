"""
Provider-neutral ports for the video pre-production kernel (Phase 6).

Every model-backed capability calls the `PreproductionModelPort` protocol.
The protocol carries a typed completion request (canonical model, temperature,
token budget, system + user prompt) and returns a typed result. No provider
SDK object, endpoint, or session leaks into the kernel. Adapters (e.g. the
OpenAI-compatible adapter or a deterministic fake) implement this port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from windagent_intelligence.video.prompts import PromptSpec


@dataclass(frozen=True)
class ModelCompletionRequest:
    """Typed, provider-neutral LLM completion request.

    Every field is a parameter, never a provider-specific object. The
    `prompt_spec` carries the version + content hash of the exact prompt
    used, so every generated artifact is traceable.
    """

    capability: str
    system: str
    user: str
    canonical_model: str = "canonical-default"
    temperature: float = 0.7
    max_tokens: int = 2048
    prompt_spec: Optional[PromptSpec] = None
    structured_output_schema: Optional[dict] = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ModelCompletionResult:
    """Typed, provider-neutral LLM completion result."""

    capability: str
    content: str
    finish_reason: str = "stop"
    provider: str = "unknown"
    usage: dict = field(default_factory=dict)


@runtime_checkable
class PreproductionModelPort(Protocol):
    """Port for model completions used by pre-production capabilities."""

    async def complete(self, request: ModelCompletionRequest) -> ModelCompletionResult:
        """Complete a single prompt; returns typed content (never raises on model I/O)."""
        ...


@runtime_checkable
class ModelDiscoveryPort(Protocol):
    """Port that exposes which canonical models a provider can serve."""

    def available_models(self) -> List[str]:
        """Return canonical model identifiers this provider can serve."""
        ...


__all__ = [
    "ModelCompletionRequest",
    "ModelCompletionResult",
    "PreproductionModelPort",
    "ModelDiscoveryPort",
]
