"""Bridge connecting SocialResearchWorkflow to native V3 Provider Adapters."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from windagent_core.contracts.providers import ProviderRequest, ProviderResponse
from windagent_providers.factory import (
    create_google_gemini_provider_adapter,
    create_ollama_provider_adapter,
)
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.ollama import OllamaProviderAdapter


class V3ModelGatewayBridge:
    """Gateway bridge adapting V3 native provider adapters for workflow model routing."""

    def __init__(
        self,
        *,
        ollama_adapter: Optional[OllamaProviderAdapter] = None,
        google_adapter: Optional[GoogleGeminiProviderAdapter] = None,
        adapters: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.adapters: Dict[str, Any] = adapters or {}
        if "ollama" not in self.adapters:
            self.adapters["ollama"] = ollama_adapter or create_ollama_provider_adapter(
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            )
        if "google" not in self.adapters:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            self.adapters["google"] = (
                google_adapter
                or create_google_gemini_provider_adapter(api_key=api_key)
            )

    async def discover_models(self, provider: str) -> List[Any]:
        """Preflight discovery check querying provider endpoint capability."""
        adapter = self.adapters.get(provider)
        if not adapter:
            raise RuntimeError(f"No V3 provider adapter configured for provider '{provider}'")

        if hasattr(adapter, "list_models"):
            return await adapter.list_models()
        if hasattr(adapter, "discover_models"):
            return await adapter.discover_models()
        if hasattr(adapter, "get_health"):
            health = await adapter.get_health()
            if health.status != "healthy":
                raise RuntimeError(
                    f"Provider '{provider}' health check failed: {health.message}"
                )
            return []

        raise RuntimeError(
            f"Provider adapter '{provider}' does not support model discovery"
        )

    async def generate(
        self,
        *,
        provider: str,
        model: str,
        system_instruction: str,
        prompt: str,
        max_output_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> ProviderResponse:
        """Execute a generation call via V3 provider adapter returning canonical ProviderResponse."""
        adapter = self.adapters.get(provider)
        if not adapter:
            raise RuntimeError(f"No V3 provider adapter registered for '{provider}'")

        request = ProviderRequest(
            system_instruction=system_instruction,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_output_tokens,
            temperature=temperature,
        )

        response: ProviderResponse = await adapter.generate(request, model_id=model)
        return response
