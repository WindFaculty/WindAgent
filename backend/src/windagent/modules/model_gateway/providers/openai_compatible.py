"""OpenAI-compatible transport: the shared driver for the compatible vendors.

EXTRACT_LOGIC of the frozen ``providers/windagent_providers/openai_compatible/transport.py``.
Preserved semantics: payload construction (system message at index 0,
``max_output_tokens``/``max_tokens`` collapse to ``max_tokens``, structured
output as ``json_schema`` response format, provider extensions merged
verbatim), the status-code error taxonomy with 400 keyword dispatch, usage
extraction including reasoning/cached tokens, ``x-request-id`` request
identity, SSE streaming with tool-call delta accumulation, and discovery via
``GET /models``.
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
    ContentPolicyFailure,
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


def _redact(text: str, api_key: str | None) -> str:
    """Strip the credential from any text before it can reach logs."""
    if api_key and api_key in text:
        return text.replace(api_key, "[redacted]")
    return text


class OpenAICompatibleTransport:
    """Core transport driver for OpenAI-compatible APIs.

    ``http_client`` is injectable so tests can drive the full pipeline with
    a mocked transport; when omitted a per-call client is created and closed.
    """

    def __init__(
        self,
        provider_name: str = "openai_compatible",
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        http_client: httpx.AsyncClient | None = None,
        stream_generate: bool = False,
        default_payload: Mapping[str, Any] | None = None,
        supports_response_format: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_headers = dict(default_headers or {})
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client
        self.stream_generate = stream_generate
        self.default_payload = dict(default_payload or {})
        # Provider-side JSON-schema enforcement hint.  Some OpenAI-compatible
        # shims distort or drop content when json_schema mode is forced; the
        # caller still validates structured output post-hoc, so dropping the
        # hint changes nothing about enforcement.
        self.supports_response_format = supports_response_format

    # ------------------------------------------------------------------ #
    # Wire helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.default_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._headers(),
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    @staticmethod
    async def _maybe_close(client: httpx.AsyncClient, owned: bool) -> None:
        if owned:
            await client.aclose()

    # ------------------------------------------------------------------ #
    # Payload construction (preserved exactly)
    # ------------------------------------------------------------------ #

    def build_payload(
        self, request: ProviderRequest, model_id: str, *, stream: bool = False
    ) -> dict[str, Any]:
        """Map a normalized request onto the ``chat/completions`` schema."""
        messages: list[dict[str, Any]] = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
        if request.prompt and not messages:
            messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": stream,
            **self.default_payload,
        }

        if request.system_instruction:
            payload["messages"].insert(
                0, {"role": "system", "content": request.system_instruction}
            )
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.seed is not None:
            payload["seed"] = request.seed

        output_limit = request.output_limit
        if output_limit is not None:
            payload["max_tokens"] = output_limit
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)
        if request.tools:
            payload["tools"] = [dict(tool) for tool in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        if request.structured_output_schema and self.supports_response_format:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": dict(request.structured_output_schema),
                },
            }
        if request.provider_extensions:
            payload.update(dict(request.provider_extensions))

        return payload

    # ------------------------------------------------------------------ #
    # Error mapping (preserved exactly)
    # ------------------------------------------------------------------ #

    def map_http_error(
        self,
        status_code: int,
        body_text: str,
        headers: Mapping[str, str] | None = None,
    ) -> ProviderFailure:
        """Translate an HTTP failure into the normalized error taxonomy."""
        clean_text = _redact(body_text, self.api_key)
        err_msg = clean_text
        try:
            parsed = json.loads(body_text)
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                raw_msg = parsed["error"].get("message")
                if isinstance(raw_msg, str) and raw_msg:
                    err_msg = _redact(raw_msg, self.api_key)
        except (json.JSONDecodeError, ValueError):
            err_msg = clean_text

        if status_code == 401:
            return AuthenticationFailure(err_msg, provider_id=self.provider_name)
        if status_code == 403:
            return PermissionFailure(err_msg, provider_id=self.provider_name)
        if status_code == 404:
            return ModelNotFoundFailure(err_msg, provider_id=self.provider_name)
        if status_code == 429:
            return RateLimitFailure(
                err_msg,
                provider_id=self.provider_name,
                context={"retry_after": retry_hint(headers)},
            )
        if status_code == 400:
            lowered = err_msg.lower()
            if "context" in lowered or "maximum context length" in lowered:
                return ContextOverflowFailure(err_msg, provider_id=self.provider_name)
            if "safety" in lowered or "content filter" in lowered:
                return ContentPolicyFailure(err_msg, provider_id=self.provider_name)
            return InvalidRequestFailure(err_msg, provider_id=self.provider_name)
        if status_code >= 500:
            return ProviderUnavailableFailure(err_msg, provider_id=self.provider_name)
        return ProviderFailure(err_msg, provider_id=self.provider_name, status_code=status_code)

    # ------------------------------------------------------------------ #
    # Completion
    # ------------------------------------------------------------------ #

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        """Execute a non-streaming completion call."""
        if self.stream_generate:
            return await self._generate_streamed(request, model_id)

        started = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        payload = self.build_payload(request, model_id, stream=False)
        client = self._client()
        owned = self._custom_client is None
        try:
            response = await client.post(url, json=payload, headers=self._headers())
            total_latency_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 200:
                raise self.map_http_error(
                    response.status_code,
                    response.text,
                    dict(response.headers),
                )

            content_type = response.headers.get("content-type", "")
            if (
                "application/json" not in content_type
                and "text/event-stream" not in content_type
            ):
                raise ProtocolMismatchFailure(
                    f"Unexpected content-type from provider: {content_type}",
                    provider_id=self.provider_name,
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise MalformedResponseFailure(
                    "Provider returned non-JSON response",
                    provider_id=self.provider_name,
                ) from exc

            return _response_from_completion(
                data=data,
                model_id=model_id,
                provider_name=self.provider_name,
                structured_schema=request.structured_output_schema,
                total_latency_ms=total_latency_ms,
                response_headers=dict(response.headers),
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            await self._maybe_close(client, owned)

    def _completion_payload(self, request: ProviderRequest, model_id: str) -> dict[str, Any]:
        payload = self.build_payload(request, model_id, stream=True)
        payload["stream_options"] = {"include_usage": True}
        return payload

    async def _generate_streamed(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        """Accumulate an SSE generation into one response (Ollama shim mode)."""
        started = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        payload = self._completion_payload(request, model_id)
        client = self._client()
        owned = self._custom_client is None

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage_data: dict[str, Any] = {}
        provider_model_id = model_id
        provider_request_id: str | None = None
        finish_reason = FinishReason.STOP.value
        accumulated_tools = _ToolCallAccumulator()

        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as response:
                if response.status_code != 200:
                    error_text = (await response.aread()).decode("utf-8", errors="replace")
                    raise self.map_http_error(
                        response.status_code, error_text, dict(response.headers)
                    )
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise ProtocolMismatchFailure(
                        f"Unexpected streaming content-type from provider: {content_type}",
                        provider_id=self.provider_name,
                    )
                provider_request_id = response.headers.get("x-request-id")
                async for chunk in _iter_sse_data(response, self.provider_name):
                    provider_request_id = provider_request_id or _as_str(chunk.get("id"))
                    provider_model_id = _as_str(chunk.get("model")) or provider_model_id
                    if isinstance(chunk.get("usage"), dict):
                        usage_data = dict(chunk["usage"])
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        content_parts.append(str(delta["content"]))
                    # Some OpenAI-compatible shims stream the whole generation
                    # under "reasoning"; keep it as a fallback so streamed
                    # answers are never silently dropped to empty content.
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                    if reasoning:
                        reasoning_parts.append(str(reasoning))
                    accumulated_tools.absorb(delta.get("tool_calls"))
                    if choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            await self._maybe_close(client, owned)

        text = "".join(content_parts) or ("".join(reasoning_parts) or None)
        tool_calls = accumulated_tools.snapshot()
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS.value
        total_latency_ms = (time.perf_counter() - started) * 1000.0
        structured = _parse_structured(text) if request.structured_output_schema else None
        return ProviderResponse(
            provider_model_id=provider_model_id,
            text=text,
            tool_calls=tool_calls,
            structured_output=structured,
            finish_reason=finish_reason,
            usage=_usage_from_openai(usage_data),
            provider_request_id=provider_request_id,
            total_latency_ms=total_latency_ms,
            raw_metadata={"mode": "streamed"},
        )

    # ------------------------------------------------------------------ #
    # Streaming (event-level)
    # ------------------------------------------------------------------ #

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Yield normalized stream events; failures before any token raise."""
        url = f"{self.base_url}/chat/completions"
        payload = self._completion_payload(request, model_id)
        client = self._client()
        owned = self._custom_client is None
        sequence = 0
        finish_reason: str | None = None
        final_usage: ProviderUsage | None = None
        accumulated_tools = _ToolCallAccumulator()

        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as response:
                if response.status_code != 200:
                    error_text = (await response.aread()).decode("utf-8", errors="replace")
                    raise self.map_http_error(
                        response.status_code, error_text, dict(response.headers)
                    )
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise ProtocolMismatchFailure(
                        f"Unexpected streaming content-type from provider: {content_type}",
                        provider_id=self.provider_name,
                    )
                async for chunk in _iter_sse_data(response, self.provider_name):
                    usage_data = chunk.get("usage")
                    if isinstance(usage_data, dict):
                        final_usage = _usage_from_openai(usage_data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        sequence += 1
                        yield ProviderStreamEvent(
                            event_type=StreamEventType.TOKEN,
                            sequence_number=sequence,
                            delta=str(content),
                        )
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                    if reasoning:
                        sequence += 1
                        yield ProviderStreamEvent(
                            event_type=StreamEventType.THINKING_DELTA,
                            sequence_number=sequence,
                            reasoning_delta=str(reasoning),
                        )
                    if delta.get("tool_calls"):
                        for call in accumulated_tools.absorb(delta["tool_calls"]):
                            sequence += 1
                            yield ProviderStreamEvent(
                                event_type=StreamEventType.TOOL_CALL_DELTA,
                                sequence_number=sequence,
                                tool_call_delta=call,
                            )
                    if choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            await self._maybe_close(client, owned)

        if finish_reason is not None or final_usage is not None:
            sequence += 1
            yield ProviderStreamEvent(
                event_type=StreamEventType.DONE,
                sequence_number=sequence,
                finish_reason=finish_reason,
                usage=final_usage,
            )

    # ------------------------------------------------------------------ #
    # Discovery and health
    # ------------------------------------------------------------------ #

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        """Discover models via ``GET /models``."""
        client = self._client()
        owned = self._custom_client is None
        try:
            response = await client.get(f"{self.base_url}/models", headers=self._headers())
            if response.status_code != 200:
                raise self.map_http_error(
                    response.status_code, response.text, dict(response.headers)
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise MalformedResponseFailure(
                    "Provider returned non-JSON discovery payload",
                    provider_id=self.provider_name,
                ) from exc
            models: list[DiscoveredModel] = []
            entries = data.get("data") if isinstance(data, dict) else None
            for entry in entries or []:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                context_window = entry.get("context_length") or entry.get("context_window")
                models.append(
                    DiscoveredModel(
                        id=str(entry["id"]),
                        context_window=int(context_window) if context_window else None,
                        raw_pricing={
                            key: value
                            for key, value in entry.items()
                            if "price" in str(key).lower()
                        },
                    )
                )
            return tuple(models)
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                _redact(f"Network error connecting to {self.base_url}: {exc}", self.api_key),
                provider_id=self.provider_name,
            ) from exc
        finally:
            await self._maybe_close(client, owned)

    async def health(self) -> HealthReport:
        """Probe health with a real discovery call (preserved behavior)."""
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


def retry_hint(headers: Mapping[str, str] | None) -> float | None:
    """Surface a parsed Retry-After hint alongside rate-limit failures."""
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _as_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _parse_structured(text: str | None) -> object:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _usage_from_openai(usage_data: Mapping[str, Any]) -> ProviderUsage:
    details = usage_data.get("completion_tokens_details")
    prompt_details = usage_data.get("prompt_tokens_details")
    return ProviderUsage(
        prompt_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage_data.get("completion_tokens", 0) or 0),
        cached_tokens=int(
            (prompt_details or {}).get("cached_tokens", 0) or 0
        ),
        reasoning_tokens=int(
            (details or {}).get("reasoning_tokens", 0) or 0
        ),
    )


def _response_from_completion(
    *,
    data: Mapping[str, Any],
    model_id: str,
    provider_name: str,
    structured_schema: Mapping[str, Any] | None,
    total_latency_ms: float,
    response_headers: Mapping[str, str],
) -> ProviderResponse:
    choices = data.get("choices") or [{}]
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    text_content = message.get("content")
    raw_tools = message.get("tool_calls") or []
    tool_calls = tuple(
        ProviderToolCall(
            id=_as_str(tool.get("id")),
            name=str((tool.get("function") or {}).get("name", "")),
            arguments=str((tool.get("function") or {}).get("arguments", "")),
        )
        for tool in raw_tools
        if isinstance(tool, dict)
    )

    structured = None
    if structured_schema and isinstance(text_content, str):
        structured = _parse_structured(text_content)

    finish_reason = choice.get("finish_reason") or FinishReason.STOP.value
    if raw_tools:
        finish_reason = FinishReason.TOOL_CALLS.value

    return ProviderResponse(
        provider_model_id=_as_str(data.get("model")) or model_id,
        text=text_content if isinstance(text_content, str) else None,
        tool_calls=tool_calls,
        structured_output=structured,
        finish_reason=str(finish_reason),
        usage=_usage_from_openai(data.get("usage") or {}),
        provider_request_id=(
            response_headers.get("x-request-id") or _as_str(data.get("id"))
        ),
        total_latency_ms=total_latency_ms,
        raw_metadata={
            "status_code": 200,
            "response_id": data.get("id"),
            "checked_at": datetime.now(UTC).isoformat(),
        },
    )


async def _iter_sse_data(
    response: httpx.Response, provider_name: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield parsed JSON objects from an SSE ``data:`` line stream."""
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
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
            yield parsed


class _ToolCallAccumulator:
    """Fragments streamed tool-call deltas keyed by their index."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, Any]] = {}

    def absorb(self, raw_deltas: object) -> list[ProviderToolCall]:
        """Absorb one ``delta.tool_calls`` fragment batch per touched index.

        Returns the accumulated state of every index touched by this batch,
        which is the normalized ``tool_call_delta`` event stream consumers
        expect (each event carries the call built so far).
        """
        touched: list[ProviderToolCall] = []
        if not isinstance(raw_deltas, list):
            return touched
        for fragment in raw_deltas:
            if not isinstance(fragment, dict):
                continue
            index = int(fragment.get("index", 0) or 0)
            slot = self._calls.setdefault(index, {"name": "", "arguments": "", "id": None})
            if fragment.get("id"):
                slot["id"] = str(fragment["id"])
            function = fragment.get("function") or {}
            if isinstance(function, dict):
                if function.get("name"):
                    slot["name"] += str(function["name"])
                if function.get("arguments"):
                    slot["arguments"] += str(function["arguments"])
            touched.append(
                ProviderToolCall(
                    id=slot["id"],
                    name=slot["name"],
                    arguments=slot["arguments"],
                )
            )
        return touched

    def snapshot(self) -> tuple[ProviderToolCall, ...]:
        """Return every accumulated tool call in index order."""
        return tuple(
            ProviderToolCall(
                id=slot["id"],
                name=slot["name"],
                arguments=slot["arguments"],
            )
            for _, slot in sorted(self._calls.items())
            if slot["name"]
        )


# --------------------------------------------------------------------------- #
# Thin vendor variants (default headers only, preserved from the old tree)
# --------------------------------------------------------------------------- #


class OpenAIProviderAdapter(OpenAICompatibleTransport):
    """OpenAI with optional organization scoping."""

    def __init__(
        self,
        api_key: str | None = None,
        organization: str | None = None,
        **kwargs: Any,
    ) -> None:
        headers = dict(kwargs.pop("default_headers", None) or {})
        if organization:
            headers["OpenAI-Organization"] = organization
        super().__init__(
            provider_name="openai",
            base_url=kwargs.pop("base_url", "https://api.openai.com/v1"),
            api_key=api_key,
            default_headers=headers,
            **kwargs,
        )


class OpenRouterAdapter(OpenAICompatibleTransport):
    """OpenRouter attribution headers."""

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        headers = dict(kwargs.pop("default_headers", None) or {})
        headers.setdefault("HTTP-Referer", "https://windagent.ai")
        headers.setdefault("X-Title", "WindAgent")
        super().__init__(
            provider_name="openrouter",
            base_url=kwargs.pop("base_url", "https://openrouter.ai/api/v1"),
            api_key=api_key,
            default_headers=headers,
            **kwargs,
        )


class MistralProviderAdapter(OpenAICompatibleTransport):
    """Mistral's OpenAI-compatible surface."""

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            provider_name="mistral",
            base_url=kwargs.pop("base_url", "https://api.mistral.ai/v1"),
            api_key=api_key,
            **kwargs,
        )


class NvidiaNimAdapter(OpenAICompatibleTransport):
    """NVIDIA NIM's OpenAI-compatible surface."""

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            provider_name="nvidia",
            base_url=kwargs.pop(
                "base_url", "https://integrate.api.nvidia.com/v1"
            ),
            api_key=api_key,
            **kwargs,
        )
