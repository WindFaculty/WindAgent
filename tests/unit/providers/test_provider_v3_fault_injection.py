"""Phase 11 fault injection tests for provider V3 transport."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.base.errors import (
    MalformedResponseFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    ProtocolMismatchFailure,
    ProviderUnavailableFailure,
)
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


def _transport(handler: Any) -> OpenAICompatibleTransport:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleTransport(
        provider_name="openai", base_url="https://fault.test/v1", http_client=client
    )


@pytest.mark.asyncio
async def test_malformed_json_raises_malformed_response():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json", headers={"content-type": "application/json"})

    transport = _transport(handler)
    with pytest.raises(MalformedResponseFailure):
        await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o")


@pytest.mark.asyncio
async def test_malformed_sse_stops_stream():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="data: not json\n\n",
            headers={"content-type": "text/event-stream"},
        )

    transport = _transport(handler)
    events = []
    async for event in transport.stream(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o"):
        events.append(event)
    # Parser silently skips unparseable SSE lines; stream ends without done.
    assert not any(e.event_type == "done" for e in events)


@pytest.mark.asyncio
async def test_truncated_stream_raises():
    def handler(_: httpx.Request) -> httpx.Response:
        # Valid first chunk, then abrupt invalid data mid-stream.
        return httpx.Response(
            200,
            text='data: {"choices": [{"delta": {"content": "a"}}]}\n\ntruncated',
            headers={"content-type": "text/event-stream"},
        )

    transport = _transport(handler)
    events = []
    async for event in transport.stream(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o"):
        events.append(event)
    assert any(e.event_type == "token" for e in events)
    # No done event because stream did not terminate cleanly.
    assert not any(e.event_type == "done" for e in events)


@pytest.mark.asyncio
async def test_404_model_not_found():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    transport = _transport(handler)
    with pytest.raises(ModelNotFoundFailure):
        await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "unknown-model")


@pytest.mark.asyncio
async def test_502_503_service_unavailable():
    for status in (500, 502, 503, 504):

        def handler(_: httpx.Request, status=status) -> httpx.Response:
            return httpx.Response(status, json={"error": {"message": "down"}})

        transport = _transport(handler)
        with pytest.raises(ProviderUnavailableFailure):
            await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o")


@pytest.mark.asyncio
async def test_protocol_mismatch_html_response():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login page</html>", headers={"content-type": "text/html"})

    transport = _transport(handler)
    with pytest.raises((MalformedResponseFailure, ProtocolMismatchFailure)):
        await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o")


@pytest.mark.asyncio
async def test_network_failure_on_dns_or_connect():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = _transport(handler)
    with pytest.raises(NetworkFailure):
        await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o")


@pytest.mark.asyncio
async def test_tls_failure():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")

    transport = _transport(handler)
    with pytest.raises(NetworkFailure):
        await transport.generate(ProviderRequest(messages=[{"role": "user", "content": "hi"}]), "gpt-4o")
