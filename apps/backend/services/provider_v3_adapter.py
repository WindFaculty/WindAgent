"""Thin wrapper turning legacy backend provider clients into V3 provider adapters.

Legacy clients expose chat_completion(model_id, messages, ...).
This adapter maps that to windagent_providers V3 ProviderRequest/ProviderResponse.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from windagent_providers.base.contracts import (
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderUsage,
)


class LegacyClientV3Adapter:
    """Wrap any legacy cloud/Ollama client for the V3 execution coordinator."""

    def __init__(self, provider_name: str, client: Any, model_id: str):
        self.provider_name = provider_name
        self._client = client
        self._model_id = model_id

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        messages: List[Dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.extend(request.messages)

        try:
            text = await self._client.chat_completion(
                model_id=model_id,
                messages=messages,
                max_tokens=request.max_output_tokens,
                temperature=request.temperature
                if request.temperature is not None
                else 1.0,
            )
        except Exception:
            # Let execution coordinator's error classification deal with it.
            raise

        return ProviderResponse(
            canonical_model_id="",
            provider_model_id=model_id,
            text=text if isinstance(text, str) else str(text),
            usage=ProviderUsage(
                prompt_tokens=sum(len(m.get("content", "").split()) for m in messages),
                completion_tokens=len(str(text).split()),
            ),
        )

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        # Stream with legacy client: generate full text, then emit as one token chunk.
        response = await self.generate(request, model_id)
        text = response.text or ""
        yield ProviderStreamEvent(event_type="token", sequence_number=1, delta=text)
        yield ProviderStreamEvent(
            event_type="done", sequence_number=2, finish_reason="stop"
        )
