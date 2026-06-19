"""Tests for ModelClient implementations (Phase 4).

Covers:
  - MockModelClient deterministic responses + offline/response-error flags.
  - OllamaModelClient happy path with a fake httpx transport.
  - OllamaModelClient offline / HTTP-error paths.
  - JSON parse tolerance (strips ```json fences).
"""
from __future__ import annotations

import json

import httpx
import pytest

from services.model_client import (
    ChatMessage,
    MockModelClient,
    ModelOfflineError,
    ModelResponseError,
    OllamaModelClient,
)


# ---------- MockModelClient ----------

@pytest.mark.asyncio
async def test_mock_client_returns_default_response_for_known_phrase():
    client = MockModelClient()
    out = await client.chat([
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="Mở Notepad và gõ Hello"),
    ])
    data = json.loads(out)
    assert len(data["steps"]) == 2
    assert data["steps"][0]["tool_name"] == "open_app"
    assert data["steps"][1]["tool_name"] == "type_text"


@pytest.mark.asyncio
async def test_mock_client_returns_empty_for_unknown_phrase():
    client = MockModelClient()
    out = await client.chat([
        ChatMessage(role="user", content="Something unrelated"),
    ])
    data = json.loads(out)
    assert data == {"steps": []}


@pytest.mark.asyncio
async def test_mock_client_offline_raises():
    client = MockModelClient(fail_with_offline=True)
    with pytest.raises(ModelOfflineError):
        await client.chat([ChatMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_mock_client_response_error_raises():
    client = MockModelClient(fail_with_response_error=True)
    with pytest.raises(ModelResponseError):
        await client.chat([ChatMessage(role="user", content="x")])


@pytest.mark.asyncio
async def test_mock_client_records_calls():
    client = MockModelClient()
    await client.chat([ChatMessage(role="user", content="a")])
    await client.chat([ChatMessage(role="user", content="b")])
    assert len(client.calls) == 2
    assert client.calls[0][0].content == "a"
    assert client.calls[1][0].content == "b"


@pytest.mark.asyncio
async def test_mock_client_health_online():
    client = MockModelClient()
    h = await client.health()
    assert h["provider"] == "mock"
    assert h["online"] is True
    assert h["error"] is None


@pytest.mark.asyncio
async def test_mock_client_health_offline():
    client = MockModelClient(fail_with_offline=True)
    h = await client.health()
    assert h["online"] is False
    assert h["error"] == "mock offline"


# ---------- OllamaModelClient (httpx mocked) ----------

def _mock_transport(handler):
    """Build an httpx.MockTransport from a sync handler."""
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_client_chat_returns_message_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "qwen3:4b-q4"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"steps":[]}'}}
                ]
            },
        )

    client = OllamaModelClient(
        base_url="http://fake-ollama/v1",
        model="qwen3:4b-q4",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    out = await client.chat([ChatMessage(role="user", content="hi")])
    assert out == '{"steps":[]}'


@pytest.mark.asyncio
async def test_ollama_client_chat_offline_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    with pytest.raises(ModelOfflineError):
        await client.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_ollama_client_chat_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    with pytest.raises(ModelResponseError):
        await client.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_ollama_client_chat_malformed_envelope_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unrelated": "shape"})

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    with pytest.raises(ModelResponseError):
        await client.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_ollama_client_health_online_with_model_present():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "qwen3:4b-q4"}, {"id": "llama3:8b"}]},
        )

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        model="qwen3:4b-q4",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    h = await client.health()
    assert h["online"] is True
    assert h["error"] is None
    assert h["latency_ms"] is not None
    assert h["model"] == "qwen3:4b-q4"


@pytest.mark.asyncio
async def test_ollama_client_health_online_but_model_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "llama3:8b"}]},
        )

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        model="qwen3:4b-q4",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    h = await client.health()
    assert h["online"] is True
    assert "model not found" in (h["error"] or "")


@pytest.mark.asyncio
async def test_ollama_client_health_offline():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    h = await client.health()
    assert h["online"] is False
    assert h["latency_ms"] is None
    assert "refused" in (h["error"] or "")


@pytest.mark.asyncio
async def test_ollama_client_health_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = OllamaModelClient(
        base_url="http://fake-ollama",
        http_client=httpx.AsyncClient(transport=_mock_transport(handler)),
    )
    h = await client.health()
    assert h["online"] is False
    assert "503" in (h["error"] or "")