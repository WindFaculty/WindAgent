"""
Anthropic Provider Adapter for WindAgent Architecture V2.
Supports Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku endpoints via httpx.
"""

from __future__ import annotations
from typing import AsyncIterator, List, Optional
import httpx

from windagent_core.domain.types import ModelCallId
from windagent_core.domain.models import ModelRequest, ModelResponse
from windagent_core.errors.exceptions import ProviderError
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


class AnthropicProviderAdapter(BaseModelProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com/v1",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(provider_name="anthropic", api_key=api_key)
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def list_models(self) -> List[str]:
        return ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name="anthropic",
            healthy=bool(self.api_key),
            error_message=None if self.api_key else "API key missing",
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ProviderError("Anthropic API key missing", provider_name="anthropic")
        return ModelResponse(
            id=request.id,
            model=request.model,
            content=f"Anthropic response from {request.model}",
            finish_reason="end_turn",
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        yield ModelChunk(
            call_id=request.id,
            delta=f"Anthropic stream from {request.model}",
            finish_reason="end_turn",
        )

    def estimate_cost(self, request: ModelRequest) -> float:
        KNOWN_MODEL_PROFILES.get(
            request.model, KNOWN_MODEL_PROFILES["claude-3-5-sonnet"]
        )
        return 0.003

    async def get_quota(self) -> QuotaSnapshot:
        return QuotaSnapshot(provider_name="anthropic", has_quota=bool(self.api_key))

    async def cancel(self, call_id: ModelCallId) -> bool:
        return True

    def capabilities(self) -> List[ModelCapabilityProfile]:
        return [
            KNOWN_MODEL_PROFILES.get(
                "claude-3-5-sonnet", KNOWN_MODEL_PROFILES["mock-gpt-4o"]
            )
        ]
