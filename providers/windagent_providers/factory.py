"""Explicit provider infrastructure factory (Architecture V3 Phase B hardening).

This module is the SINGLE allowlisted construction point for concrete provider
adapters inside the providers package. Infrastructure may DEFINE concrete
adapters anywhere, but instantiating them for wiring happens here (or in an
application composition root) so the dependency direction stays auditable:

    composition root / factory  ->  concrete adapter  ->  core port

Provider modules that lazily build a default adapter (gateway bridge, local
probing, endpoint resolution, management probes) construct it through these
creators instead of hard-instantiating adapter classes inline.
"""

from __future__ import annotations

from typing import Optional

import httpx

from windagent_providers.anthropic.adapter import AnthropicProviderAdapter
from windagent_providers.assets.fake import (
    FakeGeneratorAdapter,
    FakeInternetAssetAdapter,
)
from windagent_providers.google.adapter import GoogleGeminiProviderAdapter
from windagent_providers.ollama.adapter import OllamaProviderAdapter


def create_ollama_provider_adapter(
    *,
    base_url: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> OllamaProviderAdapter:
    return OllamaProviderAdapter(base_url=base_url, http_client=http_client)


def create_google_gemini_provider_adapter(
    *,
    api_key: str = "",
    base_url: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> GoogleGeminiProviderAdapter:
    kwargs: dict = {"api_key": api_key}
    if base_url is not None:
        kwargs["base_url"] = base_url
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    if http_client is not None:
        kwargs["http_client"] = http_client
    return GoogleGeminiProviderAdapter(**kwargs)


def create_anthropic_provider_adapter(
    *,
    api_key: str = "",
    base_url: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> AnthropicProviderAdapter:
    kwargs: dict = {"api_key": api_key}
    if base_url is not None:
        kwargs["base_url"] = base_url
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    if http_client is not None:
        kwargs["http_client"] = http_client
    return AnthropicProviderAdapter(**kwargs)


def create_fake_internet_asset_adapter() -> FakeInternetAssetAdapter:
    """Deterministic fake asset adapter (test double) — construction stays in the factory."""
    return FakeInternetAssetAdapter()


def create_fake_generator_adapter(*, enabled: bool = True) -> FakeGeneratorAdapter:
    """Deterministic fake generator adapter (test double) — construction stays in the factory."""
    return FakeGeneratorAdapter(enabled=enabled)


__all__ = [
    "create_anthropic_provider_adapter",
    "create_fake_generator_adapter",
    "create_fake_internet_asset_adapter",
    "create_google_gemini_provider_adapter",
    "create_ollama_provider_adapter",
]
