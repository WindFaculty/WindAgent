"""Anthropic Messages API adapter.

EXTRACT_LOGIC of the frozen ``providers/windagent_providers/anthropic/adapter.py``:
``POST /v1/messages`` with ``x-api-key`` + ``anthropic-version`` headers,
``system`` passed as a top-level field, tools mapped to ``input_schema``,
``stop_reason`` normalization, cache-aware usage extraction, SSE streaming
with ``content_block_delta`` parsing, and the "prompt is too long" context
overflow classification.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from ..domain.errors import (
    AuthenticationFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    MalformedResponseFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    PermissionFailure,
    ProtocolMismatchFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from .contracts import (
    DiscoveredModel,
    FinishReason,
    HealthReport,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderToolCall,
    ProviderUsage,
    StreamEventType,
)

DEFAULT_TIMEOUT_S = 30.0
ANTHROPIC_VERSION = "2023-06-01"
STOP_REASON_MAP: Mapping[str, str] = {
    "end_turn": FinishReason.STOP.value,
    "stop_sequence": FinishReason.STOP.value,
    "max_tokens": FinishReason.LENGTH.value,
    "tool_use": FinishReason.TOOL_CALLS.value,
    "refusal": FinishReason.CONTENT_FILTER.value,
}


def _redact(text: str, api_key: str | None) -> str:
    if api_key and api_key in text:
        return text.replace(api_key, "[redacted]")
    return text


class AnthropicProviderAdapter:
    """Native Anthropic Messages transport."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        anthropic_version: str = ANTHROPIC_VERSION,
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider_name = "anthropic"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.anthropic_version = anthropic_version
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.anthropic_version,
            # Preserved caching beta: prompt-caching header stays opt-in on
            # every request so cacheable prefixes keep their discounts.
            "anthropic-beta": "prompt-caching-2024-07-31",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._headers(), timeout=httpx.Timeout(self.timeout_seconds)
        )

    def build_payload(self, request: ProviderRequest, model_id: str) -> dict[str, Any]:
        """Map a normalized request onto the Anthropic Messages schema."""
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "tool":
                entry = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id or "",
                            "content": message.content,
                        }
                    ],
                }
            messages.append(entry)
        if request.prompt and not messages:
            messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.output_limit or 1024,
        }
        if request.system_instruction:
            payload["system"] = request.system_instruction
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop_sequences:
            payload["stop_sequences"] = list(request.stop_sequences)
        if request.tools:
            payload["tools"] = [
                {
                    "name": str(tool.get("name", "")),
                    "description": str(tool.get("description", "")),
                    "input_schema": dict(tool.get("input_schema") or tool.get("parameters") or {}),
                }
                for tool in request.tools
            ]
        if request.tool_choice is not None:
            choice = request.tool_choice
            if isinstance(choice, str):
                payload["tool_choice"] = {"type": "auto" if choice == "auto" else "any"}
            elif isinstance(choice, Mapping):
                payload["tool_choice"] = dict(choice)
        if request.provider_extensions:
            payload.update(dict(request.provider_extensions))
        return payload

    def map_http_error(self, status_code: int, body_text: str) -> ProviderFailure:
        """Translate an Anthropic HTTP failure into the taxonomy."""
        message = _redact(body_text, self.api_key)
        try:
            parsed = json.loads(body_text)
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                detail = parsed["error"].get("message")
                if isinstance(detail, str) and detail:
                    message = _redact(detail, self.api_key)
        except ValueError:
            message = _redact(body_text, self.api_key)

        lowered = message.lower()
        if status_code in (401, 403):
            if status_code == 401:
                return AuthenticationFailure(message, provider_id=self.provider_name)
            return PermissionFailure(message, provider_id=self.provider_name)
        if status_code == 404:
            return ModelNotFoundFailure(message, provider_id=self.provider_name)
        if status_code == 429:
            return RateLimitFailure(message, provider_id=self.provider_name)
        if status_code == 400:
            if "prompt is too long" in lowered or "context" in lowered:
                return ContextOverflowFailure(message, provider_id=self.provider_name)
            return InvalidRequestFailure(message, provider_id=self.provider_name)
        if status_code >= 500:
            return ProviderUnavailableFailure(message, provider_id=self.provider_name)
        return ProviderFailure(
            message, provider_id=self.provider_name, status_code=status_code
        )

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        """Execute one Messages API completion."""
        started = time.perf_counter()
        url = f"{self.base_url}/messages"
        payload = self.build_payload(request, model_id)
        client = self._client()
        owned = self._custom_client is None
        try:
            response = await client.post(url, json=payload, headers=self._headers())
            total_latency_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 200:
                raise self.map_http_error(response.status_code, response.text)
            try:
                data = response.json()
            except ValueError as exc:
                raise MalformedResponseFailure(
                    "Provider returned non-JSON response",
                    provider_id=self.provider_name,
                ) from exc
            return _response_from_message(
                data=data,
                model_id=model_id,
                structured_schema=request.structured_output_schema,
                total_latency_ms=total_latency_ms,
                request_id=response.headers.get("request-id"),
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}", provider_id=self.provider_name
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            if owned:
                await client.aclose()

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Stream ``content_block_delta`` events as normalized chunks."""
        url = f"{self.base_url}/messages"
        payload = self.build_payload(request, model_id)
        payload["stream"] = True
        client = self._client()
        owned = self._custom_client is None
        sequence = 0
        finish_reason: str | None = None
        final_usage: ProviderUsage | None = None
        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as response:
                if response.status_code != 200:
                    error_text = (await response.aread()).decode("utf-8", errors="replace")
                    raise self.map_http_error(response.status_code, error_text)
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise ProtocolMismatchFailure(
                        f"Unexpected streaming content-type from provider: {content_type}",
                        provider_id=self.provider_name,
                    )
                async for chunk in _iter_sse(response, self.provider_name):
                    event_type = chunk.get("type")
                    if event_type == "content_block_delta":
                        delta = chunk.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            sequence += 1
                            yield ProviderStreamEvent(
                                event_type=StreamEventType.TOKEN,
                                sequence_number=sequence,
                                delta=str(delta["text"]),
                            )
                        elif delta.get("type") == "input_json_delta" and delta.get(
                            "partial_json"
                        ):
                            sequence += 1
                            yield ProviderStreamEvent(
                                event_type=StreamEventType.TOOL_CALL_DELTA,
                                sequence_number=sequence,
                                tool_call_delta=ProviderToolCall(
                                    id=None,
                                    name=str(chunk.get("index", 0)),
                                    arguments=str(delta["partial_json"]),
                                ),
                            )
                    elif event_type == "message_delta":
                        delta = chunk.get("delta") or {}
                        if delta.get("stop_reason"):
                            finish_reason = STOP_REASON_MAP.get(
                                str(delta["stop_reason"]), str(delta["stop_reason"])
                            )
                        usage = chunk.get("usage")
                        if isinstance(usage, dict):
                            final_usage = _usage_from_anthropic(usage, base=final_usage)
                    elif event_type == "message_start":
                        usage = (chunk.get("message") or {}).get("usage")
                        if isinstance(usage, dict):
                            final_usage = _usage_from_anthropic(usage)
                    elif event_type == "error":
                        error = chunk.get("error") or {}
                        raise ProviderFailure(
                            str(error.get("message", "stream error")),
                            provider_id=self.provider_name,
                        )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}", provider_id=self.provider_name
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            if owned:
                await client.aclose()

        sequence += 1
        yield ProviderStreamEvent(
            event_type=StreamEventType.DONE,
            sequence_number=sequence,
            finish_reason=finish_reason or FinishReason.STOP.value,
            usage=final_usage,
        )

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        """Discover models via ``GET /v1/models``."""
        client = self._client()
        owned = self._custom_client is None
        try:
            response = await client.get(f"{self.base_url}/models", headers=self._headers())
            if response.status_code != 200:
                raise self.map_http_error(response.status_code, response.text)
            try:
                data = response.json()
            except ValueError as exc:
                raise MalformedResponseFailure(
                    "Provider returned non-JSON discovery payload",
                    provider_id=self.provider_name,
                ) from exc
            return tuple(
                DiscoveredModel(id=str(entry["id"]))
                for entry in (data.get("data") or [])
                if isinstance(entry, dict) and entry.get("id")
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}", provider_id=self.provider_name
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            if owned:
                await client.aclose()

    async def health(self) -> HealthReport:
        """Probe health with a discovery call."""
        started = time.perf_counter()
        try:
            await self.list_models()
        except ProviderFailure as failure:
            return HealthReport(
                provider_name=self.provider_name,
                healthy=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                status_code=failure.status_code,
                error_message=str(failure),
                last_check_at=datetime.now(UTC),
            )
        return HealthReport(
            provider_name=self.provider_name,
            healthy=True,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            status_code=200,
            last_check_at=datetime.now(UTC),
        )


async def _iter_sse(
    response: httpx.Response, provider_name: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield parsed SSE JSON payloads including Anthropic's ``event:`` lines."""
    pending_event: str | None = None
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped:
            pending_event = None
            continue
        if stripped.startswith("event:"):
            pending_event = stripped[6:].strip()
            continue
        if stripped.startswith(":") or not stripped.startswith("data:"):
            continue
        data_text = stripped[5:].strip()
        if data_text == "[DONE]":
            continue
        try:
            parsed = json.loads(data_text)
        except ValueError as exc:
            raise MalformedResponseFailure(
                "Provider returned malformed SSE JSON",
                provider_id=provider_name,
            ) from exc
        if isinstance(parsed, dict):
            if pending_event and "type" not in parsed:
                parsed = {"type": pending_event, **parsed}
            yield parsed


def _usage_from_anthropic(
    usage: Mapping[str, Any], base: ProviderUsage | None = None
) -> ProviderUsage:
    prompt = int(usage.get("input_tokens", 0) or 0)
    completion = int(usage.get("output_tokens", 0) or 0)
    cached = int(
        (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
    )
    if base is not None:
        prompt = max(prompt, base.prompt_tokens)
        completion += base.completion_tokens
        cached = max(cached, base.cached_tokens)
    return ProviderUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_tokens=cached,
    )


def _response_from_message(
    *,
    data: Mapping[str, Any],
    model_id: str,
    structured_schema: Mapping[str, Any] | None,
    total_latency_ms: float,
    request_id: str | None,
) -> ProviderResponse:
    text_parts: list[str] = []
    tool_calls: list[ProviderToolCall] = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            text_parts.append(str(block["text"]))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                ProviderToolCall(
                    id=_as_str(block.get("id")),
                    name=str(block.get("name", "")),
                    arguments=json.dumps(block.get("input") or {}),
                )
            )

    text = "".join(text_parts) or None
    structured = None
    if structured_schema and text:
        try:
            structured = json.loads(text)
        except ValueError:
            structured = None

    stop_reason = data.get("stop_reason") or "end_turn"
    finish_reason = STOP_REASON_MAP.get(str(stop_reason), str(stop_reason))
    if tool_calls:
        finish_reason = FinishReason.TOOL_CALLS.value

    usage = _usage_from_anthropic(data.get("usage") or {})
    return ProviderResponse(
        provider_model_id=_as_str(data.get("model")) or model_id,
        text=text,
        tool_calls=tuple(tool_calls),
        structured_output=structured,
        finish_reason=finish_reason,
        usage=usage,
        provider_request_id=request_id or _as_str(data.get("id")),
        total_latency_ms=total_latency_ms,
        raw_metadata={"status_code": 200, "checked_at": datetime.now(UTC).isoformat()},
    )


def _as_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
