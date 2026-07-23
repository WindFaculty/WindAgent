"""
OpenAI-Compatible Shared Transport Engine for WindAgent Provider Subsystem V3.
Provides high-performance AsyncClient pooling, request/response codecs, SSE streaming parser,
tool call delta accumulation, status code error mapping, health probing, and model discovery.
"""

from __future__ import annotations
import json
import time
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from windagent_providers.base.contracts import (
    DiscoveredModel,
    FinishReason,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderUsage,
)
from windagent_providers.base.errors import (
    AuthenticationFailure,
    CancellationFailure,
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
from windagent_providers.base.secret_redaction import redact_text


class OpenAICompatibleTransport:
    """Core Transport Driver for OpenAI-compatible APIs."""

    def __init__(
        self,
        provider_name: str = "openai_compatible",
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_headers = default_headers or {}
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", **self.default_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    def _build_payload(
        self, request: ProviderRequest, model_id: str, stream: bool = False
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": request.messages.copy(),
            "stream": stream,
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
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if request.structured_output_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": request.structured_output_schema,
                },
            }

        # Extra provider extensions
        if request.provider_extensions:
            payload.update(request.provider_extensions)

        return payload

    def _map_http_error(
        self, status_code: int, body_text: str, response_headers: httpx.Headers
    ) -> ProviderFailure:
        clean_text = redact_text(body_text)

        try:
            err_json = json.loads(body_text)
            raw_msg = err_json.get("error", {}).get("message", clean_text)
            err_msg = redact_text(raw_msg)
        except Exception:
            err_msg = clean_text

        if status_code == 401:
            return AuthenticationFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code == 403:
            return PermissionFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code == 404:
            return ModelNotFoundFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code == 429:
            return RateLimitFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code == 400:
            if (
                "context" in err_msg.lower()
                or "maximum context length" in err_msg.lower()
            ):
                return ContextOverflowFailure(
                    err_msg, provider_id=self.provider_name, status_code=status_code
                )
            if "safety" in err_msg.lower() or "content filter" in err_msg.lower():
                return ContentPolicyFailure(
                    err_msg, provider_id=self.provider_name, status_code=status_code
                )
            return InvalidRequestFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code >= 500:
            return ProviderUnavailableFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )

        return ProviderFailure(
            err_msg, provider_id=self.provider_name, status_code=status_code
        )

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        """Executes a synchronous completion call."""
        start_time = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(request, model_id, stream=False)

        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.post(url, json=payload, headers=self._build_headers())
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text, resp.headers)

            content_type = resp.headers.get("content-type", "")
            if (
                "application/json" not in content_type
                and "text/event-stream" not in content_type
            ):
                raise ProtocolMismatchFailure(
                    f"Unexpected content-type from provider: {content_type}",
                    provider_id=self.provider_name,
                )

            try:
                data = resp.json()
            except Exception as exc:
                raise MalformedResponseFailure(
                    "Provider returned non-JSON response",
                    provider_id=self.provider_name,
                ) from exc
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})

            # Extract content & tool calls
            text_content = message.get("content")
            raw_tools = message.get("tool_calls", [])
            tool_calls = [
                {
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": tc.get("function", {}),
                }
                for tc in raw_tools
            ]

            # Structured output parsing
            structured_out = None
            if request.structured_output_schema and text_content:
                try:
                    structured_out = json.loads(text_content)
                except Exception:
                    pass

            usage_data = data.get("usage", {})
            prompt_tokens = usage_data.get("prompt_tokens", 0)
            completion_tokens = usage_data.get("completion_tokens", 0)
            details = usage_data.get("completion_tokens_details", {})
            reasoning_tokens = details.get("reasoning_tokens", 0)
            cached_tokens = usage_data.get("prompt_tokens_details", {}).get(
                "cached_tokens", 0
            )

            finish_reason_str = choice.get("finish_reason", FinishReason.STOP.value)
            if raw_tools:
                finish_reason_str = FinishReason.TOOL_CALLS.value

            return ProviderResponse(
                canonical_model_id=model_id,
                provider_model_id=data.get("model", model_id),
                endpoint_id=f"ep-{self.provider_name}",
                text=text_content,
                tool_calls=tool_calls,
                structured_output=structured_out,
                finish_reason=finish_reason_str,
                usage=ProviderUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                    reasoning_tokens=reasoning_tokens,
                ),
                provider_request_id=resp.headers.get("x-request-id") or data.get("id"),
                total_latency_ms=total_latency_ms,
                raw_metadata={
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "response_id": data.get("id"),
                },
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to {self.base_url}", provider_id=self.provider_name
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error connecting to {self.base_url}: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Executes a streaming completion call with fragmented SSE parser & tool accumulation."""
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(request, model_id, stream=True)

        client = self._get_client()
        should_close = self._custom_client is None

        seq_num = 0
        accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._build_headers()
            ) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    raise self._map_http_error(
                        resp.status_code,
                        error_text.decode("utf-8", errors="replace"),
                        resp.headers,
                    )

                buffer = ""
                async for chunk_bytes in resp.aiter_bytes():
                    buffer += chunk_bytes.decode("utf-8", errors="replace")

                    # Process SSE lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data:"):
                            data_str = line[5:].strip()

                            if data_str == "[DONE]":
                                seq_num += 1
                                yield ProviderStreamEvent(
                                    event_type="done",
                                    sequence_number=seq_num,
                                    finish_reason=FinishReason.STOP.value,
                                )
                                return

                            try:
                                data = json.loads(data_str)
                            except Exception:
                                continue

                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})

                            text_delta = delta.get("content")
                            reasoning_delta = delta.get(
                                "reasoning_content"
                            ) or delta.get("reasoning")
                            raw_tool_deltas = delta.get("tool_calls", [])
                            finish_reason = choice.get("finish_reason")

                            # Accumulate tool call deltas
                            for tc_delta in raw_tool_deltas:
                                idx = tc_delta.get("index", 0)
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {
                                        "id": tc_delta.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc_delta.get("id"):
                                    accumulated_tool_calls[idx]["id"] = tc_delta["id"]
                                func_delta = tc_delta.get("function", {})
                                if func_delta.get("name"):
                                    accumulated_tool_calls[idx]["function"]["name"] += (
                                        func_delta["name"]
                                    )
                                if func_delta.get("arguments"):
                                    accumulated_tool_calls[idx]["function"][
                                        "arguments"
                                    ] += func_delta["arguments"]

                            seq_num += 1
                            yield ProviderStreamEvent(
                                event_type="token"
                                if text_delta
                                else (
                                    "thinking_delta"
                                    if reasoning_delta
                                    else "tool_call_delta"
                                ),
                                sequence_number=seq_num,
                                delta=text_delta,
                                reasoning_delta=reasoning_delta,
                                tool_call_delta=accumulated_tool_calls.get(0)
                                if raw_tool_deltas
                                else None,
                                finish_reason=finish_reason,
                            )

        except asyncio.CancelledError:
            raise CancellationFailure(
                "Streaming request was cancelled", provider_id=self.provider_name
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout streaming from {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error streaming from {self.base_url}: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def list_models(self) -> List[DiscoveredModel]:
        """Queries /models endpoint to discover available models."""
        url = f"{self.base_url}/models"
        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.get(url, headers=self._build_headers())
            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text, resp.headers)

            data = resp.json()
            raw_models = data.get("data", [])
            results = []
            for item in raw_models:
                m_id = item.get("id", "")
                results.append(
                    DiscoveredModel(
                        raw_model_id=m_id,
                        canonical_name=m_id,
                        provider_id=self.provider_name,
                        capabilities=["chat", "streaming", "tool_use"],
                    )
                )
            return results
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout querying models from {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error querying models from {self.base_url}: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        """Executes a diagnostic health probe network call."""
        start_time = time.perf_counter()
        try:
            await self.list_models()
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return ProviderHealth(
                provider_name=self.provider_name,
                healthy=True,
                latency_ms=latency_ms,
                status_code=200,
            )
        except ProviderFailure as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return ProviderHealth(
                provider_name=self.provider_name,
                healthy=False,
                latency_ms=latency_ms,
                status_code=err.status_code,
                error_message=err.message,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return ProviderHealth(
                provider_name=self.provider_name,
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(exc),
            )
