"""Offline unit tests for provider protocol adapters (mocked HTTP transport)."""

from __future__ import annotations

import json

import httpx
import pytest
from windagent.modules.model_gateway.domain.errors import (
    AuthenticationFailure,
    ContentPolicyFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    ModelNotFoundFailure,
    PermissionFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from windagent.modules.model_gateway.providers.anthropic import AnthropicProviderAdapter
from windagent.modules.model_gateway.providers.contracts import (
    FinishReason,
    ProviderMessage,
    ProviderRequest,
    ProviderStreamEvent,
    StreamEventType,
)
from windagent.modules.model_gateway.providers.google import GoogleGeminiProviderAdapter
from windagent.modules.model_gateway.providers.ollama import OllamaProviderAdapter
from windagent.modules.model_gateway.providers.openai_compatible import (
    OpenAICompatibleTransport,
    OpenRouterAdapter,
)
from windagent.modules.model_gateway.providers.resolver import DefaultAdapterFactory


def _client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _request(**overrides: object) -> ProviderRequest:
    defaults: dict[str, object] = {
        "model_id": "",
        "messages": (ProviderMessage(role="user", content="hello"),),
        "prompt": "",
    }
    defaults.update(overrides)
    return ProviderRequest(**defaults)  # type: ignore[arg-type]


class TestOpenAIPayload:
    def test_build_payload_matches_chat_completions_schema(self) -> None:
        transport = OpenAICompatibleTransport(api_key="sk-test")
        request = _request(
            system_instruction="be brief",
            temperature=0.2,
            top_p=0.9,
            seed=7,
            max_output_tokens=128,
            stop_sequences=("END",),
            tools=({"type": "function", "function": {"name": "f"}},),
            structured_output_schema={"type": "object"},
            provider_extensions={"logit_bias": {"1": 2}},
        )
        payload = transport.build_payload(request, "gpt-4o")
        assert payload["model"] == "gpt-4o"
        assert payload["messages"][0] == {"role": "system", "content": "be brief"}
        assert payload["messages"][1] == {"role": "user", "content": "hello"}
        assert payload["temperature"] == 0.2
        assert payload["top_p"] == 0.9
        assert payload["seed"] == 7
        assert payload["max_tokens"] == 128
        assert payload["stop"] == ["END"]
        assert payload["tools"] == [{"type": "function", "function": {"name": "f"}}]
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["logit_bias"] == {"1": 2}
        assert payload["stream"] is False

    def test_prompt_becomes_a_user_message(self) -> None:
        transport = OpenAICompatibleTransport()
        payload = transport.build_payload(_request(messages=(), prompt="hi"), "m")
        assert payload["messages"] == [{"role": "user", "content": "hi"}]

    def test_error_mapping_taxonomy(self) -> None:
        transport = OpenAICompatibleTransport()
        assert isinstance(transport.map_http_error(401, "{}"), AuthenticationFailure)
        assert isinstance(transport.map_http_error(403, "{}"), PermissionFailure)
        assert isinstance(transport.map_http_error(404, "{}"), ModelNotFoundFailure)
        assert isinstance(transport.map_http_error(429, "{}"), RateLimitFailure)
        assert isinstance(
            transport.map_http_error(400, "maximum context length exceeded"),
            ContextOverflowFailure,
        )
        assert isinstance(
            transport.map_http_error(400, "safety system rejection"),
            ContentPolicyFailure,
        )
        assert isinstance(
            transport.map_http_error(400, "{}"), InvalidRequestFailure
        )
        assert isinstance(
            transport.map_http_error(503, "{}"), ProviderUnavailableFailure
        )

    def test_error_messages_are_redacted_and_parsed(self) -> None:
        transport = OpenAICompatibleTransport(api_key="sk-super-secret")
        failure = transport.map_http_error(
            401, json.dumps({"error": {"message": "bad key sk-super-secret"}})
        )
        assert isinstance(failure, AuthenticationFailure)
        assert "sk-super-secret" not in failure.message
        assert "[redacted]" in failure.message

    @pytest.mark.asyncio
    async def test_generate_extracts_usage_and_request_id(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer sk-live"
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "x-request-id": "req-1"},
                json={
                    "id": "chatcmpl-1",
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "message": {"content": "hi there"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "prompt_tokens_details": {"cached_tokens": 3},
                        "completion_tokens_details": {"reasoning_tokens": 2},
                    },
                },
            )

        transport = OpenAICompatibleTransport(
            api_key="sk-live", http_client=_client(handler)
        )
        response = await transport.generate(_request(), "gpt-4o")
        assert response.text == "hi there"
        assert response.provider_request_id == "req-1"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5
        assert response.usage.cached_tokens == 3
        assert response.usage.reasoning_tokens == 2
        assert response.finish_reason == FinishReason.STOP.value

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("boom")

        transport = OpenAICompatibleTransport(http_client=_client(handler))
        with pytest.raises(TimeoutFailure):
            await transport.generate(_request(), "m")


class TestOpenAIStreaming:
    @pytest.mark.asyncio
    async def test_stream_emits_token_and_done_events(self) -> None:
        sse = (
            'data: {"id":"c1","choices":[{"delta":{"content":"Hel"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":2}}\n\n'
            "data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=sse
            )

        transport = OpenAICompatibleTransport(http_client=_client(handler))
        events = [event async for event in transport.stream(_request(), "m")]
        assert [e.event_type for e in events] == [
            StreamEventType.TOKEN,
            StreamEventType.TOKEN,
            StreamEventType.DONE,
        ]
        assert events[0].delta == "Hel"
        assert events[-1].usage is not None
        assert events[-1].usage.completion_tokens == 2
        assert events[-1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_streamed_generation_accumulates(self) -> None:
        sse = (
            'data: {"choices":[{"delta":{"content":"abc"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"def"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":2}}\n\n'
            "data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=sse
            )

        transport = OllamaProviderAdapter(http_client=_client(handler))
        response = await transport.generate(_request(), "llama3.1")
        assert response.text == "abcdef"
        assert response.usage.completion_tokens == 2

    def test_ollama_shim_quirks_are_preserved(self) -> None:
        adapter = OllamaProviderAdapter()
        assert adapter.stream_generate is True
        assert adapter.supports_response_format is False
        assert adapter.default_payload["num_ctx"] == 16384


class TestAnthropicAdapter:
    def test_payload_uses_system_field_and_input_schema(self) -> None:
        adapter = AnthropicProviderAdapter()
        request = _request(
            system_instruction="sys",
            max_output_tokens=256,
            tools=({"name": "tool", "input_schema": {"type": "object"}},),
        )
        payload = adapter.build_payload(request, "claude-3-5-sonnet-20241022")
        assert payload["system"] == "sys"
        assert payload["max_tokens"] == 256
        assert payload["tools"][0]["input_schema"] == {"type": "object"}
        assert "system" not in payload["messages"][0]

    @pytest.mark.asyncio
    async def test_generate_maps_content_blocks_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-api-key"] == "sk-ant"
            assert request.headers["anthropic-version"] == "2023-06-01"
            return httpx.Response(
                200,
                json={
                    "id": "msg_1",
                    "model": "claude-3-5-sonnet-20241022",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "tool_use",
                            "id": "tu_1",
                            "name": "lookup",
                            "input": {"q": "x"},
                        },
                    ],
                    "stop_reason": "tool_use",
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 8,
                        "cache_read_input_tokens": 4,
                    },
                },
            )

        adapter = AnthropicProviderAdapter(api_key="sk-ant", http_client=_client(handler))
        response = await adapter.generate(_request(), "claude-3-5-sonnet-20241022")
        assert response.text == "hello"
        assert response.tool_calls[0].name == "lookup"
        assert response.finish_reason == FinishReason.TOOL_CALLS.value
        assert response.usage.prompt_tokens == 12
        assert response.usage.cached_tokens == 4

    def test_prompt_too_long_maps_to_context_overflow(self) -> None:
        adapter = AnthropicProviderAdapter()
        failure = adapter.map_http_error(400, "prompt is too long: 200 tokens > 100")
        assert isinstance(failure, ContextOverflowFailure)


class TestGoogleAdapter:
    def test_payload_uses_contents_and_gemini_schema(self) -> None:
        adapter = GoogleGeminiProviderAdapter()
        request = _request(
            messages=(
                ProviderMessage(role="user", content="hi"),
                ProviderMessage(role="assistant", content="hello"),
            ),
            system_instruction="sys",
        )
        payload = adapter.build_payload(request, "gemini-1.5-pro")
        assert payload["systemInstruction"]["parts"] == [{"text": "sys"}]
        assert payload["contents"][1]["role"] == "model"
        assert "x-goog-api-key" not in json.dumps(payload)

    @pytest.mark.asyncio
    async def test_generate_uses_header_auth_and_maps_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-goog-api-key"] == "aiza-key"
            assert "key=" not in str(request.url)
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "answer"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 6,
                        "candidatesTokenCount": 3,
                    },
                },
            )

        adapter = GoogleGeminiProviderAdapter(api_key="aiza-key", http_client=_client(handler))
        response = await adapter.generate(_request(), "gemini-1.5-pro")
        assert response.text == "answer"
        assert response.usage.prompt_tokens == 6
        assert response.usage.completion_tokens == 3


class TestResolver:
    def test_thin_vendors_and_unknown_modes(self) -> None:
        factory = DefaultAdapterFactory()
        assert isinstance(
            factory.resolve("openai", base_url="https://x/v1", api_key="k"),
            OpenAICompatibleTransport,
        )
        assert isinstance(
            factory.resolve("openrouter", base_url="https://x/v1", api_key="k"),
            OpenRouterAdapter,
        )
        with pytest.raises(InvalidRequestFailure):
            factory.resolve("skynet", base_url="https://x", api_key=None)

    @pytest.mark.asyncio
    async def test_stream_finishes_with_done(self) -> None:
        sse = 'data: {"candidates":[{"content":{"parts":[{"text":"x"}]}}]}\n\n'

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse,
            )

        adapter = GoogleGeminiProviderAdapter(http_client=_client(handler))
        events: list[ProviderStreamEvent] = []
        async for event in adapter.stream(_request(), "m"):
            events.append(event)
        assert events[-1].event_type == StreamEventType.DONE

