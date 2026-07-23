"""Thin wrapper turning legacy backend provider clients into V3 provider adapters.

Legacy clients expose chat_completion(model_id, messages, ...).
This adapter maps that to windagent_providers V3 ProviderRequest/ProviderResponse.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List

from windagent_providers.base.contracts import (
    FinishReason,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderUsage,
)

from services.provider_v3_tool_translation import (
    normalize_tool_result,
    to_anthropic_tools,
    to_ollama_tools,
    to_openai_tools,
)


class LegacyClientV3Adapter:
    """Wrap any legacy cloud/Ollama client for the V3 execution coordinator."""

    def __init__(self, provider_name: str, client: Any, model_id: str):
        self.provider_name = provider_name
        self._client = client
        self._model_id = model_id

    def _normalize_messages(
        self, request: ProviderRequest
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.extend(request.messages)
        return messages

    def _translate_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not tools:
            return []
        if self.provider_name == "anthropic":
            return to_anthropic_tools(tools)
        if self.provider_name == "ollama":
            return to_ollama_tools(tools)
        return to_openai_tools(tools)

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        messages = self._normalize_messages(request)
        payload: Dict[str, Any] = {
            "model_id": model_id,
            "messages": messages,
            "temperature": request.temperature if request.temperature is not None else 1.0,
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = self._translate_tools(request.tools)
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        try:
            raw = await self._client.chat_completion(**payload)
        except Exception:
            # Let execution coordinator's error classification deal with it.
            raise

        text: str | None = None
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = FinishReason.STOP.value

        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, dict):
            text = raw.get("content")
            raw_tools = raw.get("tool_calls", [])
            tool_calls = normalize_tool_result(raw_tools, provider=self.provider_name)
            if tool_calls:
                finish_reason = FinishReason.TOOL_CALLS.value
        else:
            text = str(raw)

        return ProviderResponse(
            canonical_model_id="",
            provider_model_id=model_id,
            text=text if isinstance(text, str) else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=ProviderUsage(
                prompt_tokens=self._estimate_tokens(messages),
                completion_tokens=self._estimate_tokens(text or "") + len(tool_calls),
            ),
        )

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        # Legacy clients do not have a real streaming API. Generate full response,
        # then emit appropriate V3 events so the coordinator/gateway can format
        # OpenAI-compatible SSE chunks.
        response = await self.generate(request, model_id)
        seq = 0
        if response.text:
            seq += 1
            yield ProviderStreamEvent(
                event_type="token", sequence_number=seq, delta=response.text
            )
        if response.tool_calls:
            for tc in response.tool_calls:
                seq += 1
                yield ProviderStreamEvent(
                    event_type="tool_call_delta",
                    sequence_number=seq,
                    tool_call_delta=tc,
                )
        seq += 1
        yield ProviderStreamEvent(
            event_type="done", sequence_number=seq, finish_reason=response.finish_reason
        )

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        if isinstance(value, list):
            return sum(len(str(m.get("content", "")).split()) for m in value)
        return len(str(value).split())
