"""
Unit tests for Native Anthropic, Google Gemini, Ollama, and Local Provider Adapters.
Adheres strictly to ban_ke_hoach.md §PHASE 4 requirements using httpx.MockTransport.
"""

import pytest
import json
import httpx

from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.anthropic import AnthropicProviderAdapter
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.ollama import OllamaProviderAdapter
from windagent_providers.local import LocalOllamaManager


@pytest.mark.asyncio
async def test_anthropic_native_generate_and_stream():
    # 1. Non-stream test
    def handler_sync(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers.get("x-api-key") == "sk-ant-test"
        payload = json.loads(request.content)
        assert payload["model"] == "claude-3-5-sonnet-20241022"
        assert len(payload["tools"]) == 1

        return httpx.Response(
            200,
            json={
                "id": "msg_0112345",
                "model": "claude-3-5-sonnet-20241022",
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Analyzing codebase..."},
                    {"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {"path": "main.py"}}
                ],
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 40,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 50
                }
            },
            headers={"request-id": "req-ant-1"}
        )

    client_sync = httpx.AsyncClient(transport=httpx.MockTransport(handler_sync))
    anthropic = AnthropicProviderAdapter(api_key="sk-ant-test", http_client=client_sync)

    req = ProviderRequest(
        messages=[{"role": "user", "content": "Read main.py"}],
        tools=[{"function": {"name": "read_file", "parameters": {"type": "object"}}}]
    )
    resp = await anthropic.generate(req)

    assert resp.canonical_model_id == "claude-3-5-sonnet-20241022"
    assert resp.text == "Analyzing codebase..."
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["function"]["name"] == "read_file"
    assert resp.usage.prompt_tokens == 150
    assert resp.usage.completion_tokens == 40
    assert resp.usage.cached_tokens == 50
    assert resp.finish_reason == "tool_calls"

    # 2. SSE Stream test
    sse_body = (
        'event: message_start\n'
        'data: {"type":"message_start","message":{"id":"msg_100"}}\n\n'
        'event: content_block_start\n'
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        'event: content_block_delta\n'
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello Anthropic"}}\n\n'
        'event: message_stop\n'
        'data: {"type":"message_stop"}\n\n'
    )

    def handler_stream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    client_stream = httpx.AsyncClient(transport=httpx.MockTransport(handler_stream))
    anthropic_stream = AnthropicProviderAdapter(api_key="sk-ant-test", http_client=client_stream)

    events = []
    async for evt in anthropic_stream.stream(req):
        events.append(evt)

    assert len(events) == 2
    assert events[0].delta == "Hello Anthropic"
    assert events[1].event_type == "done"


@pytest.mark.asyncio
async def test_google_gemini_native_generate_and_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/models/gemini-1.5-pro:generateContent" in request.url.path
        payload = json.loads(request.content)
        assert payload["contents"][0]["role"] == "user"

        return httpx.Response(
            200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Gemini response text"}]
                    },
                    "finishReason": "STOP",
                    "safetyRatings": [{"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"}]
                }],
                "usageMetadata": {
                    "promptTokenCount": 25,
                    "candidatesTokenCount": 12
                }
            }
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gemini = GoogleGeminiProviderAdapter(api_key="AIzaSyTestKey", http_client=mock_client)

    req = ProviderRequest(messages=[{"role": "user", "content": "Hello Gemini"}])
    resp = await gemini.generate(req, model_id="gemini-1.5-pro")

    assert resp.canonical_model_id == "gemini-1.5-pro"
    assert resp.text == "Gemini response text"
    assert resp.usage.prompt_tokens == 25
    assert resp.usage.completion_tokens == 12
    assert resp.finish_reason == "stop"


@pytest.mark.asyncio
async def test_google_gemini_uses_single_turn_prompt_field():
    """Canonical ProviderRequest carries user text in ``prompt`` with
    messages=[] (RouteLockedModelPort). Without this the API rejects the
    call with "contents is not specified"."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        parts = payload["contents"][0]["parts"]
        assert payload["contents"][0]["role"] == "user"
        assert parts[0]["text"] == "Viết kịch bản tiếng Việt"
        assert payload["systemInstruction"]["parts"][0]["text"] == "Bạn là biên kịch"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gemini = GoogleGeminiProviderAdapter(api_key="AIzaSyTestKey", http_client=mock_client)

    req = ProviderRequest(
        model_id="gemini-3.5-flash-lite",
        prompt="Viết kịch bản tiếng Việt",
        messages=[],
        system_instruction="Bạn là biên kịch",
        temperature=None,
        max_output_tokens=64,
    )
    resp = await gemini.generate(req, model_id="gemini-3.5-flash-lite")

    assert resp.text == "ok"
    assert resp.provider_model_id == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_ollama_native_generate_stream_and_tokens_per_sec():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "Ollama local response"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 20,
                "eval_count": 50,
                "eval_duration": 1000000000  # 1 second in ns -> 50.0 tokens/sec
            }
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaProviderAdapter(base_url="http://localhost:11434", http_client=mock_client)

    req = ProviderRequest(messages=[{"role": "user", "content": "Hello Ollama"}])
    resp = await ollama.generate(req, model_id="llama3.1")

    assert resp.canonical_model_id == "llama3.1"
    assert resp.text == "Ollama local response"
    assert resp.usage.prompt_tokens == 20
    assert resp.usage.completion_tokens == 50
    assert resp.raw_metadata["tokens_per_sec"] == 50.0


@pytest.mark.asyncio
async def test_ollama_health_fail_when_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "Ollama server offline"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaProviderAdapter(base_url="http://localhost:11434", http_client=mock_client)

    health = await ollama.health()
    assert health.healthy is False
    assert health.status_code == 503
    assert health.error_message is not None


@pytest.mark.asyncio
async def test_local_ollama_lan_reachability():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "192.168.1.50":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:32b"}]})
        return httpx.Response(500, json={"error": "Connection refused"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    lan_manager = LocalOllamaManager(
        endpoints=["http://192.168.1.99:11434", "http://192.168.1.50:11434"],
        http_client=mock_client
    )

    healthy_ep = await lan_manager.get_healthy_endpoint()
    assert healthy_ep == "http://192.168.1.50:11434"
