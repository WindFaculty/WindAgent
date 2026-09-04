"""Adapter resolution: protocol mode plus endpoint config to a transport.

REWRITE of the frozen ``endpoint_adapter_resolver`` with the old timeouts and
per-protocol classes preserved: 300s for Ollama and Gemini (long local or
long-generation surfaces), 30s for the cloud chat vendors.
"""

from __future__ import annotations

from typing import Final

from .anthropic import AnthropicProviderAdapter
from .contracts import ProviderAdapter
from .google import GoogleGeminiProviderAdapter
from .ollama import OllamaProviderAdapter
from .openai_compatible import (
    MistralProviderAdapter,
    NvidiaNimAdapter,
    OpenAICompatibleTransport,
    OpenRouterAdapter,
)

DEFAULT_TIMEOUT_S: Final[float] = 30.0
LOCAL_TIMEOUT_S: Final[float] = 300.0

SUPPORTED_PROTOCOLS: Final[frozenset[str]] = frozenset(
    {
        "openai",
        "openai_compatible",
        "openrouter",
        "mistral",
        "nvidia",
        "ollama",
        "anthropic",
        "google",
        "gemini",
    }
)


class DefaultAdapterFactory:
    """Builds one adapter per attempt from resolved endpoint settings.

    The API key arrives already revealed by the caller — the single
    credential use boundary — and is never stored on the factory.
    """

    def resolve(
        self,
        protocol_mode: str,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float | None = None,
    ) -> ProviderAdapter:
        """Return the transport for ``protocol_mode``."""
        mode = (protocol_mode or "openai").strip().lower()
        if mode == "anthropic":
            return AnthropicProviderAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_S,
            )
        if mode in ("google", "gemini"):
            return GoogleGeminiProviderAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds or LOCAL_TIMEOUT_S,
            )
        if mode == "ollama":
            return OllamaProviderAdapter(
                base_url=base_url,
                timeout_seconds=timeout_seconds or LOCAL_TIMEOUT_S,
            )
        if mode == "openrouter":
            return OpenRouterAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_S,
            )
        if mode == "mistral":
            return MistralProviderAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_S,
            )
        if mode == "nvidia":
            return NvidiaNimAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_S,
            )
        if mode in ("openai", "openai_compatible"):
            return OpenAICompatibleTransport(
                provider_name=mode,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_S,
            )
        from ..domain.errors import InvalidRequestFailure

        raise InvalidRequestFailure(
            f"unsupported provider protocol mode: {protocol_mode!r}",
            context={"protocol_mode": protocol_mode},
        )
