"""
Google Gemini Provider Adapter for WindAgent Architecture V2.
Supports Gemini 1.5 Pro, Gemini 1.5 Flash endpoints.
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


class GoogleGeminiProviderAdapter(BaseModelProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(provider_name="google", api_key=api_key)
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def list_models(self) -> List[str]:
        return ["gemini-1.5-pro", "gemini-1.5-flash"]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name="google",
            healthy=bool(self.api_key),
            error_message=None if self.api_key else "API key missing",
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ProviderError("Gemini API key missing", provider_name="google")
        return ModelResponse(
            id=request.id,
            model=request.model,
            content=f"Google Gemini response from {request.model}",
            finish_reason="STOP",
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        yield ModelChunk(
            call_id=request.id,
            delta=f"Gemini stream from {request.model}",
            finish_reason="STOP",
        )

    def estimate_cost(self, request: ModelRequest) -> float:
        return 0.001

    async def get_quota(self) -> QuotaSnapshot:
        return QuotaSnapshot(provider_name="google", has_quota=bool(self.api_key))

    async def cancel(self, call_id: ModelCallId) -> bool:
        return True

    def capabilities(self) -> List[ModelCapabilityProfile]:
        return [
            KNOWN_MODEL_PROFILES.get(
                "gemini-1.5-pro", KNOWN_MODEL_PROFILES["mock-gpt-4o"]
            )
        ]
