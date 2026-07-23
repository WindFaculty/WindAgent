# tests/unit/providers/test_provider_v3_adapter.py
from __future__ import annotations

import pytest

from windagent_providers.base.contracts import FinishReason, ProviderRequest
from services.provider_v3_adapter import LegacyClientV3Adapter


class _FakeLegacyClient:
    def __init__(self, provider_name: str, response_text: str = "", tool_calls=None):
        self.provider_name = provider_name
        self._response_text = response_text
        self._tool_calls = tool_calls or []
        self.last_payload: dict | None = None

    async def chat_completion(self, **kwargs):
        self.last_payload = kwargs
        if self._tool_calls:
            return {"content": self._response_text, "tool_calls": self._tool_calls}
        return self._response_text


@pytest.mark.asyncio
async def test_adapter_forwards_tools_openai_format():
    client = _FakeLegacyClient("openai")
    adapter = LegacyClientV3Adapter("openai", client, model_id="gpt-4o")
    request = ProviderRequest(
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "..."},
            }
        ],
        tool_choice="auto",
    )
    response = await adapter.generate(request, "gpt-4o")
    assert client.last_payload is not None
    assert len(client.last_payload["tools"]) == 1
    assert client.last_payload["tools"][0]["type"] == "function"
    assert client.last_payload["tools"][0]["function"]["name"] == "get_weather"
    assert client.last_payload["tool_choice"] == "auto"
    assert response.finish_reason == FinishReason.STOP.value


@pytest.mark.asyncio
async def test_adapter_extracts_text_only_legacy_string():
    client = _FakeLegacyClient("openai", response_text="hello")
    adapter = LegacyClientV3Adapter("openai", client, model_id="gpt-4o")
    response = await adapter.generate(ProviderRequest(messages=[]), "gpt-4o")
    assert response.text == "hello"
    assert response.finish_reason == FinishReason.STOP.value


@pytest.mark.asyncio
async def test_adapter_extracts_tool_calls_from_legacy_dict():
    client = _FakeLegacyClient(
        "openai",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"Hanoi"}'},
            }
        ],
    )
    adapter = LegacyClientV3Adapter("openai", client, model_id="gpt-4o")
    response = await adapter.generate(ProviderRequest(messages=[]), "gpt-4o")
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["function"]["name"] == "get_weather"
    assert response.finish_reason == FinishReason.TOOL_CALLS.value


@pytest.mark.asyncio
async def test_adapter_stream_emits_tool_call_event():
    client = _FakeLegacyClient(
        "anthropic",
        tool_calls=[
            {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"location": "Hanoi"}}
        ],
    )
    adapter = LegacyClientV3Adapter("anthropic", client, model_id="claude-sonnet")
    events = []
    async for event in adapter.stream(ProviderRequest(messages=[]), "claude-sonnet"):
        events.append(event)
    assert any(e.event_type == "tool_call_delta" for e in events)
    assert any(e.event_type == "done" for e in events)
