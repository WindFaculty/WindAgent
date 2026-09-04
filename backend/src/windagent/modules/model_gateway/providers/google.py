"""Google Gemini adapter.

EXTRACT_LOGIC of the frozen ``providers/windagent_providers/google/adapter.py``:
``POST /models/{model}:generateContent`` with the ``x-goog-api-key`` header
(never a query string, to keep keys out of logs), ``contents``/``parts``
mapping with role normalization (assistant → ``model``), ``systemInstruction``
separation, ``inlineData`` image parts, ``functionDeclarations`` tools,
``finishReason`` normalization (SAFETY/RECITATION → content filter), and
``usageMetadata`` accounting.
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
    ImagePart,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderToolCall,
    ProviderUsage,
    StreamEventType,
)

DEFAULT_TIMEOUT_S = 30.0
FINISH_REASON_MAP: Mapping[str, str] = {
    "STOP": FinishReason.STOP.value,
    "MAX_TOKENS": FinishReason.LENGTH.value,
    "SAFETY": FinishReason.CONTENT_FILTER.value,
    "RECITATION": FinishReason.CONTENT_FILTER.value,
    "BLOCKLIST": FinishReason.CONTENT_FILTER.value,
    "PROHIBITED_CONTENT": FinishReason.CONTENT_FILTER.value,
    "MALFORMED_FUNCTION_CALL": FinishReason.ERROR.value,
}


def _redact(text: str, api_key: str | None) -> str:
    if api_key and api_key in text:
        return text.replace(api_key, "[redacted]")
    return text


class GoogleGeminiProviderAdapter:
    """Native Gemini generateContent transport."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider_name = "google"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # The key travels only in the header; query-string auth leaks keys
        # into access logs and was explicitly rejected in the old system.
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    def _client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._headers(), timeout=httpx.Timeout(self.timeout_seconds)
        )

    def build_payload(self, request: ProviderRequest, model_id: str) -> dict[str, Any]:
        """Map a normalized request onto the Gemini generateContent schema."""
        contents: list[dict[str, Any]] = []
        for message in request.messages:
            role = "model" if message.role == "assistant" else "user"
            parts: list[dict[str, Any]] = [{"text": message.content}]
            contents.append({"role": role, "parts": parts})
        if request.prompt and not contents:
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        for image in request.image_parts:
            contents.append({"role": "user", "parts": [_inline_data(image)]})

        payload: dict[str, Any] = {"contents": contents}
        if request.system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }

        generation_config: dict[str, Any] = {}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.top_p is not None:
            generation_config["topP"] = request.top_p
        if request.seed is not None:
            generation_config["seed"] = request.seed
        output_limit = request.output_limit
        if output_limit is not None:
            generation_config["maxOutputTokens"] = output_limit
        if request.stop_sequences:
            generation_config["stopSequences"] = list(request.stop_sequences)
        if request.structured_output_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = dict(request.structured_output_schema)
        if generation_config:
            payload["generationConfig"] = generation_config

        if request.tools:
            declarations = [
                {
                    "name": str(tool.get("name", "")),
                    "description": str(tool.get("description", "")),
                    "parameters": dict(
                        tool.get("input_schema") or tool.get("parameters") or {}
                    ),
                }
                for tool in request.tools
            ]
            payload["tools"] = [{"functionDeclarations": declarations}]
        if request.provider_extensions:
            payload.update(dict(request.provider_extensions))
        return payload

    def map_http_error(self, status_code: int, body_text: str) -> ProviderFailure:
        """Translate a Gemini HTTP failure into the taxonomy."""
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
            # Gemini answers unauthorized keys with either status; both mean
            # the credential is unusable.
            return AuthenticationFailure(message, provider_id=self.provider_name)
        if status_code == 404:
            return ModelNotFoundFailure(message, provider_id=self.provider_name)
        if status_code == 429:
            return RateLimitFailure(message, provider_id=self.provider_name)
        if status_code == 400:
            if "context" in lowered or ("token" in lowered and "limit" in lowered):
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
        """Execute one generateContent call."""
        started = time.perf_counter()
        url = f"{self.base_url}/models/{model_id}:generateContent"
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
            return _response_from_generate(
                data=data,
                model_id=model_id,
                structured_schema=request.structured_output_schema,
                total_latency_ms=total_latency_ms,
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
        """Stream via ``:streamGenerateContent?alt=sse``."""
        url = f"{self.base_url}/models/{model_id}:streamGenerateContent?alt=sse"
        payload = self.build_payload(request, model_id)
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
                    usage = chunk.get("usageMetadata")
                    if isinstance(usage, dict):
                        final_usage = _usage_from_gemini(usage)
                    candidates = chunk.get("candidates") or []
                    if not candidates:
                        continue
                    candidate = (
                        candidates[0] if isinstance(candidates[0], dict) else {}
                    )
                    content = candidate.get("content") or {}
                    for part in content.get("parts") or []:
                        if not isinstance(part, dict):
                            continue
                        if part.get("text"):
                            sequence += 1
                            yield ProviderStreamEvent(
                                event_type=StreamEventType.TOKEN,
                                sequence_number=sequence,
                                delta=str(part["text"]),
                            )
                        elif part.get("functionCall"):
                            call = dict(part["functionCall"])
                            sequence += 1
                            yield ProviderStreamEvent(
                                event_type=StreamEventType.TOOL_CALL_DELTA,
                                sequence_number=sequence,
                                tool_call_delta=ProviderToolCall(
                                    id=None,
                                    name=str(call.get("name", "")),
                                    arguments=json.dumps(call.get("args") or {}),
                                ),
                            )
                    if candidate.get("finishReason"):
                        finish_reason = FINISH_REASON_MAP.get(
                            str(candidate["finishReason"]),
                            str(candidate["finishReason"]),
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
        """Discover models via ``GET /models``."""
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
            models: list[DiscoveredModel] = []
            for entry in data.get("models") or []:
                if not isinstance(entry, dict):
                    continue
                raw_name = str(entry.get("name", ""))
                if not raw_name:
                    continue
                model_id = raw_name.split("models/", 1)[-1]
                input_limit = entry.get("inputTokenLimit")
                models.append(
                    DiscoveredModel(
                        id=model_id,
                        context_window=int(input_limit) if input_limit else None,
                    )
                )
            return tuple(models)
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


def _inline_data(image: ImagePart) -> dict[str, Any]:
    return {"inlineData": {"mimeType": image.mime_type, "data": image.data}}


async def _iter_sse(
    response: httpx.Response, provider_name: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield parsed SSE JSON payloads."""
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


def _usage_from_gemini(usage: Mapping[str, Any]) -> ProviderUsage:
    return ProviderUsage(
        prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
        completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
        cached_tokens=int(usage.get("cachedContentTokenCount", 0) or 0),
    )


def _response_from_generate(
    *,
    data: Mapping[str, Any],
    model_id: str,
    structured_schema: Mapping[str, Any] | None,
    total_latency_ms: float,
) -> ProviderResponse:
    candidates = data.get("candidates") or [{}]
    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    content = candidate.get("content") or {}

    text_parts: list[str] = []
    tool_calls: list[ProviderToolCall] = []
    for part in content.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if part.get("text"):
            text_parts.append(str(part["text"]))
        elif part.get("functionCall"):
            call = dict(part["functionCall"])
            tool_calls.append(
                ProviderToolCall(
                    id=None,
                    name=str(call.get("name", "")),
                    arguments=json.dumps(call.get("args") or {}),
                )
            )

    text = "".join(text_parts) or None
    structured = None
    if structured_schema and text:
        try:
            structured = json.loads(text)
        except ValueError:
            structured = None

    raw_reason = str(candidate.get("finishReason", "STOP"))
    finish_reason = FINISH_REASON_MAP.get(raw_reason, raw_reason)
    if tool_calls:
        finish_reason = FinishReason.TOOL_CALLS.value

    return ProviderResponse(
        provider_model_id=model_id,
        text=text,
        tool_calls=tuple(tool_calls),
        structured_output=structured,
        finish_reason=finish_reason,
        usage=_usage_from_gemini(data.get("usageMetadata") or {}),
        provider_request_id=_as_str(data.get("responseId")),
        total_latency_ms=total_latency_ms,
        raw_metadata={"status_code": 200, "checked_at": datetime.now(UTC).isoformat()},
    )


def _as_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
