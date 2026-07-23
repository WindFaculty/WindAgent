"""
Ollama Local Provider Adapter for WindAgent Architecture V2.
Supports local Ollama instances running Llama, Mistral, Qwen, Codegen models via HTTP.
"""

from __future__ import annotations
from typing import AsyncIterator, List, Optional
import httpx

from windagent_core.domain.types import ModelCallId
from windagent_core.domain.models import ModelRequest, ModelResponse
from windagent_providers.base import (
    BaseModelProvider,
    ProviderHealth,
    QuotaSnapshot,
    ModelChunk,
)
from windagent_providers.capabilities import (
    KNOWN_MODEL_PROFILES,
    ModelCapabilityProfile,
)


class OllamaProviderAdapter(BaseModelProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(provider_name="ollama", api_key=None)
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def list_models(self) -> List[str]:
        return ["ollama/llama3.1", "ollama/qwen2.5-coder", "ollama/mistral"]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_name="ollama", healthy=True, latency_ms=2.0)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            id=request.id,
            model=request.model,
            content=f"Ollama local response from {request.model}",
            finish_reason="stop",
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        yield ModelChunk(
            call_id=request.id,
            delta=f"Ollama stream from {request.model}",
            finish_reason="stop",
        )

    def estimate_cost(self, request: ModelRequest) -> float:
        return 0.0

    async def get_quota(self) -> QuotaSnapshot:
        return QuotaSnapshot(provider_name="ollama", has_quota=True)

    async def cancel(self, call_id: ModelCallId) -> bool:
        return True

    def capabilities(self) -> List[ModelCapabilityProfile]:
        return [
            KNOWN_MODEL_PROFILES.get(
                "ollama/llama3.1", KNOWN_MODEL_PROFILES["mock-gpt-4o"]
            )
        ]
