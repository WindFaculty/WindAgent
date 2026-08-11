"""
Unit tests for OpenAI-Compatible Shared Transport Core and Thin Vendor Adapters.
Adheres strictly to ban_ke_hoach.md §PHASE 3 requirements using httpx.MockTransport.
"""

import pytest
import json
import httpx

from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.base.errors import (
    AuthenticationFailure, RateLimitFailure,
    ModelNotFoundFailure, ProviderUnavailableFailure
)
from windagent_providers.openai_compatible import OpenAICompatibleTransport
from windagent_providers.openai import OpenAIProviderAdapter
from windagent_providers.openrouter import OpenRouterAdapter
from windagent_providers.nvidia import NvidiaNimAdapter
from windagent_providers.mistral import MistralProviderAdapter


def test_payload_uses_canonical_max_tokens_and_prefers_explicit_output_limit():
    transport = OpenAICompatibleTransport(api_key="sk-testkey")

    payload = transport._build_payload(  # noqa: SLF001 - transport contract regression
        ProviderRequest(prompt="bounded", max_tokens=4000),
        "ornith:9b",
    )
    assert payload["max_tokens"] == 4000

    payload = transport._build_payload(  # noqa: SLF001 - precedence is intentional
        ProviderRequest(prompt="bounded", max_tokens=4000, max_output_tokens=1200),
        "ornith:9b",
    )
    assert payload["max_tokens"] == 1200


@pytest.mark.asyncio
async def test_non_stream_completion_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-4o"
        assert payload["messages"][0]["content"] == "Hello OpenAI"

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-12345",
                "model": "gpt-4o-2024-05-13",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello user!"},
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            },
            headers={"x-request-id": "req-xyz-100"}
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = OpenAICompatibleTransport(api_key="sk-testkey", http_client=mock_client)
    
    req = ProviderRequest(messages=[{"role": "user", "content": "Hello OpenAI"}])
    response = await transport.generate(req, model_id="gpt-4o")

    assert response.canonical_model_id == "gpt-4o"
    assert response.provider_model_id == "gpt-4o-2024-05-13"
    assert response.text == "Hello user!"
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    assert response.provider_request_id == "req-xyz-100"


@pytest.mark.asyncio
async def test_streamed_generate_accumulates_content_usage_and_request_id():
    sse_body = (
        'data: {"id":"chatcmpl-real-1","model":"ornith:9b","choices":'
        '[{"delta":{"content":"{\\"ok\\":"},"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-real-1","model":"ornith:9b","choices":'
        '[{"delta":{"content":"true}"},"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-real-1","model":"ornith:9b","choices":[],"usage":'
        '{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["messages"][-1] == {
            "role": "user",
            "content": "Return JSON",
        }
        assert payload["stream_options"] == {"include_usage": True}
        assert payload["think"] is False
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = OpenAICompatibleTransport(
        provider_name="ollama-local",
        http_client=mock_client,
        stream_generate=True,
        default_payload={"think": False},
    )
    request = ProviderRequest(
        prompt="Return JSON",
        structured_output_schema={"type": "object", "required": ["ok"]},
    )

    response = await transport.generate(request, model_id="ornith:9b")

    assert response.text == '{"ok":true}'
    assert response.structured_output == {"ok": True}
    assert response.provider_model_id == "ornith:9b"
    assert response.provider_request_id == "chatcmpl-real-1"
    assert response.usage.prompt_tokens == 7
    assert response.usage.completion_tokens == 3
    assert response.raw_metadata["streamed_generation"] is True


@pytest.mark.asyncio
async def test_stream_completion_fragmented_sse_and_tool_calls():
    # SSE stream simulation with fragmented chunks and tool call deltas
    sse_body = (
        'data: {"choices": [{"delta": {"role": "assistant"}, "finish_reason": null}]}\n\n'
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_999", "function": {"name": "get_weather"}}]}, "finish_reason": null}]}\n\n'
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"location\\": \\"Tokyo\\""}}]}, "finish_reason": null}]}\n\n'
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}, "finish_reason": "tool_calls"}]}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = OpenAICompatibleTransport(api_key="sk-testkey", http_client=mock_client)
    
    req = ProviderRequest(messages=[{"role": "user", "content": "What is the weather in Tokyo?"}])
    
    events = []
    async for evt in transport.stream(req, model_id="gpt-4o"):
        events.append(evt)

    assert len(events) == 5
    assert events[-1].event_type == "done"
    
    # Check tool call accumulation event
    tool_event = events[2]
    assert tool_event.tool_call_delta is not None
    assert tool_event.tool_call_delta["id"] == "call_999"
    assert tool_event.tool_call_delta["function"]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_error_status_code_mappings():
    # 401 AuthenticationFailure
    handler_401 = lambda r: httpx.Response(401, json={"error": {"message": "Invalid API key sk-secret12345"}})
    t_401 = OpenAICompatibleTransport(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_401)))
    with pytest.raises(AuthenticationFailure) as exc_info:
        await t_401.generate(ProviderRequest(), model_id="gpt-4o")
    assert "sk-secret12345" not in str(exc_info.value)  # Secret redacted

    # 404 ModelNotFoundFailure
    handler_404 = lambda r: httpx.Response(404, json={"error": {"message": "Model not found"}})
    t_404 = OpenAICompatibleTransport(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_404)))
    with pytest.raises(ModelNotFoundFailure):
        await t_404.generate(ProviderRequest(), model_id="nonexistent-model")

    # 429 RateLimitFailure
    handler_429 = lambda r: httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}}, headers={"retry-after": "5"})
    t_429 = OpenAICompatibleTransport(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_429)))
    with pytest.raises(RateLimitFailure) as exc_429:
        await t_429.generate(ProviderRequest(), model_id="gpt-4o")
    assert exc_429.value.retryable is True

    # 503 ProviderUnavailableFailure
    handler_503 = lambda r: httpx.Response(503, json={"error": {"message": "Server overloaded"}})
    t_503 = OpenAICompatibleTransport(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_503)))
    with pytest.raises(ProviderUnavailableFailure):
        await t_503.generate(ProviderRequest(), model_id="gpt-4o")


@pytest.mark.asyncio
async def test_live_health_probe_and_model_discovery():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={
            "data": [
                {"id": "gpt-4o", "object": "model"},
                {"id": "gpt-4o-mini", "object": "model"}
            ]
        })

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = OpenAICompatibleTransport(api_key="sk-testkey", http_client=mock_client)

    discovered = await transport.list_models()
    assert len(discovered) == 2
    assert discovered[0].raw_model_id == "gpt-4o"
    assert discovered[1].raw_model_id == "gpt-4o-mini"

    health = await transport.health()
    assert health.healthy is True
    assert health.status_code == 200
    assert health.latency_ms > 0.0


@pytest.mark.asyncio
async def test_vendor_adapters_share_transport():
    # Test OpenAI adapter
    openai_adapter = OpenAIProviderAdapter(api_key="sk-openai-key", organization="org-123")
    assert openai_adapter.provider_name == "openai"
    assert openai_adapter.base_url == "https://api.openai.com/v1"
    assert openai_adapter.default_headers["OpenAI-Organization"] == "org-123"

    # Test OpenRouter adapter
    openrouter_adapter = OpenRouterAdapter(api_key="sk-or-key")
    assert openrouter_adapter.provider_name == "openrouter"
    assert openrouter_adapter.base_url == "https://openrouter.ai/api/v1"
    assert openrouter_adapter.default_headers["X-Title"] == "WindAgent"

    # Test NVIDIA adapter
    nvidia_adapter = NvidiaNimAdapter(api_key="nvapi-key")
    assert nvidia_adapter.provider_name == "nvidia"
    assert nvidia_adapter.base_url == "https://integrate.api.nvidia.com/v1"

    # Test Mistral adapter
    mistral_adapter = MistralProviderAdapter(api_key="mistral-key")
    assert mistral_adapter.provider_name == "mistral"
    assert mistral_adapter.base_url == "https://api.mistral.ai/v1"
