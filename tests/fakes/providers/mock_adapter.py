"""
Mock Provider Adapter for WindAgent Architecture V2.
100% offline, zero-network adapter for unit tests and local development.
"""

from __future__ import annotations
from typing import AsyncIterator, List

from windagent_core.domain.types import ModelCallId
from windagent_core.domain.models import ModelRequest, ModelResponse
from tests.support.waiting import async_deterministic_sleep

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


class MockProviderAdapter(BaseModelProvider):
    def __init__(self, mock_response: str = "Mock response content"):
        super().__init__(provider_name="mock", api_key="mock-key-12345")
        self.mock_response = mock_response
        self._active_calls: set[str] = set()

    async def list_models(self) -> List[str]:
        return ["mock-gpt-4o", "mock-llama-3"]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name="mock",
            healthy=True,
            latency_ms=1.5,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._active_calls.add(str(request.id))
        try:
            await async_deterministic_sleep(0.01)
            content = f"{self.mock_response} for model {request.model}"
            return ModelResponse(
                id=request.id,
                model=request.model,
                content=content,
                finish_reason="stop",
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            )
        finally:
            self._active_calls.discard(str(request.id))

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        self._active_calls.add(str(request.id))
        words = self.mock_response.split()
        try:
            for idx, word in enumerate(words):
                if str(request.id) not in self._active_calls:
                    break
                await async_deterministic_sleep(0.005)
                yield ModelChunk(
                    call_id=request.id,
                    delta=f"{word} ",
                    finish_reason="stop" if idx == len(words) - 1 else None,
                )
        finally:
            self._active_calls.discard(str(request.id))

    def estimate_cost(self, request: ModelRequest) -> float:
        return 0.0001

    async def get_quota(self) -> QuotaSnapshot:
        return QuotaSnapshot(
            provider_name="mock",
            has_quota=True,
            remaining_tokens=1000000,
            remaining_requests=1000,
        )

    async def cancel(self, call_id: ModelCallId) -> bool:
        if str(call_id) in self._active_calls:
            self._active_calls.discard(str(call_id))
            return True
        return False

    def capabilities(self) -> List[ModelCapabilityProfile]:
        return [KNOWN_MODEL_PROFILES["mock-gpt-4o"]]