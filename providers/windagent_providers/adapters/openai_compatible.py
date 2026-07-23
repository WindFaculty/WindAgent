"""
OpenAI-Compatible Provider Adapter for WindAgent Architecture V2.
Supports OpenAI, OpenRouter, DeepSeek, and local VLLM endpoints via httpx.
"""

from __future__ import annotations
import json
import logging
from typing import AsyncIterator, Dict, List, Optional
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

logger = logging.getLogger("windagent.providers.openai")


class OpenAICompatibleProviderAdapter(BaseModelProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(provider_name=provider_name, api_key=api_key)
        self.base_url = base_url.rstrip("/")
        self._client = client

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def list_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]

    async def health(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(
                provider_name=self.provider_name,
                healthy=False,
                error_message="API key missing",
            )
        return ProviderHealth(
            provider_name=self.provider_name,
            healthy=True,
            latency_ms=15.0,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        headers = self._get_headers()

        try:
            if self._client:
                resp = await self._client.post(
                    url, json=payload, headers=headers, timeout=30.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        url, json=payload, headers=headers, timeout=30.0
                    )

            if resp.status_code != 200:
                raise ProviderError(
                    message=f"OpenAI API returned status {resp.status_code}: {resp.text}",
                    provider_name=self.provider_name,
                    status_code=resp.status_code,
                    retryable=(resp.status_code in (429, 500, 502, 503, 504)),
                )

            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason", "stop")
            usage = data.get("usage", {})

            return ModelResponse(
                id=request.id,
                model=request.model,
                content=content,
                finish_reason=finish_reason,
                usage=usage,
            )
        except httpx.RequestError as e:
            raise ProviderError(
                message=f"Network error communicating with {self.provider_name}: {e}",
                provider_name=self.provider_name,
                retryable=True,
            )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": True,
        }
        headers = self._get_headers()

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers, timeout=60.0
            ) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        message=f"OpenAI streaming status {response.status_code}",
                        provider_name=self.provider_name,
                        status_code=response.status_code,
                    )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            delta = chunk_json["choices"][0]["delta"].get("content", "")
                            finish = chunk_json["choices"][0].get("finish_reason")
                            if delta or finish:
                                yield ModelChunk(
                                    call_id=request.id,
                                    delta=delta,
                                    finish_reason=finish,
                                )
                        except json.JSONDecodeError:
                            continue

    def estimate_cost(self, request: ModelRequest) -> float:
        profile = KNOWN_MODEL_PROFILES.get(
            request.model, KNOWN_MODEL_PROFILES["gpt-4o"]
        )
        # Estimate ~4 chars per token
        prompt_len = sum(len(str(m.get("content", ""))) for m in request.messages)
        prompt_tokens = max(1, prompt_len // 4)
        completion_tokens = request.max_tokens or 500
        return (prompt_tokens / 1000.0) * profile.cost_per_1k_prompt_tokens + (
            completion_tokens / 1000.0
        ) * profile.cost_per_1k_completion_tokens

    async def get_quota(self) -> QuotaSnapshot:
        return QuotaSnapshot(
            provider_name=self.provider_name,
            has_quota=bool(self.api_key),
        )

    async def cancel(self, call_id: ModelCallId) -> bool:
        return True

    def capabilities(self) -> List[ModelCapabilityProfile]:
        return [KNOWN_MODEL_PROFILES.get("gpt-4o", KNOWN_MODEL_PROFILES["mock-gpt-4o"])]
