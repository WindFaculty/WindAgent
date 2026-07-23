"""
Native Anthropic Provider Adapter for WindAgent Provider Subsystem V3.
Implements native Messages API (POST /v1/messages), tool use, prompt caching,
and real SSE event parsing without OpenAI compatibility wrappers.
"""

from __future__ import annotations
import json
import time
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from windagent_providers.base.contracts import (
    DiscoveredModel, FinishReason, ProviderCapabilities, ProviderHealth,
    ProviderRequest, ProviderResponse, ProviderStreamEvent, ProviderUsage
)
from windagent_providers.base.errors import (
    AuthenticationFailure, CancellationFailure, ContextOverflowFailure,
    InvalidRequestFailure, ModelNotFoundFailure, NetworkFailure,
    PermissionFailure, ProviderFailure, ProviderUnavailableFailure, RateLimitFailure,
    TimeoutFailure
)
from windagent_providers.base.secret_redaction import redact_text, redact_dict


class AnthropicProviderAdapter:
    """Native Anthropic Messages API Adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com/v1",
        anthropic_version: str = "2023-06-01",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = "anthropic"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.anthropic_version = anthropic_version
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.anthropic_version,
            "anthropic-beta": "prompt-caching-2024-07-31",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    def _build_messages_payload(self, request: ProviderRequest, model_id: str, stream: bool = False) -> Dict[str, Any]:
        messages = []
        for msg in request.messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                continue  # System prompt passed separately in Anthropic
            messages.append({"role": role, "content": content})

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.max_output_tokens or 4096,
            "stream": stream,
        }

        if request.system_instruction:
            payload["system"] = request.system_instruction

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences

        if request.tools:
            anthropic_tools = []
            for t in request.tools:
                fn = t.get("function", t)
                anthropic_tools.append({
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}})
                })
            payload["tools"] = anthropic_tools

        return payload

    def _map_http_error(self, status_code: int, body_text: str) -> ProviderFailure:
        clean_text = redact_text(body_text)
        try:
            err_json = json.loads(body_text)
            err_msg = redact_text(err_json.get("error", {}).get("message", clean_text))
        except Exception:
            err_msg = clean_text

        if status_code == 401:
            return AuthenticationFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
        elif status_code == 403:
            return PermissionFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
        elif status_code == 404:
            return ModelNotFoundFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
        elif status_code == 429:
            return RateLimitFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
        elif status_code == 400:
            if "prompt is too long" in err_msg.lower() or "maximum context" in err_msg.lower():
                return ContextOverflowFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
            return InvalidRequestFailure(err_msg, provider_id=self.provider_name, status_code=status_code)
        elif status_code >= 500:
            return ProviderUnavailableFailure(err_msg, provider_id=self.provider_name, status_code=status_code)

        return ProviderFailure(err_msg, provider_id=self.provider_name, status_code=status_code)

    async def generate(self, request: ProviderRequest, model_id: str = "claude-3-5-sonnet-20241022") -> ProviderResponse:
        """Executes a synchronous completion call using Anthropic Messages API."""
        start_time = time.perf_counter()
        url = f"{self.base_url}/messages"
        payload = self._build_messages_payload(request, model_id, stream=False)

        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.post(url, json=payload, headers=self._build_headers())
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            content_blocks = data.get("content", [])

            text_parts = []
            tool_calls = []

            for block in content_blocks:
                b_type = block.get("type")
                if b_type == "text":
                    text_parts.append(block.get("text", ""))
                elif b_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}))
                        }
                    })

            usage_raw = data.get("usage", {})
            input_tokens = usage_raw.get("input_tokens", 0)
            output_tokens = usage_raw.get("output_tokens", 0)
            cache_creation = usage_raw.get("cache_creation_input_tokens", 0)
            cache_read = usage_raw.get("cache_read_input_tokens", 0)

            stop_reason = data.get("stop_reason")
            finish_reason_val = FinishReason.STOP.value
            if stop_reason == "tool_use" or tool_calls:
                finish_reason_val = FinishReason.TOOL_CALLS.value
            elif stop_reason == "max_tokens":
                finish_reason_val = FinishReason.LENGTH.value

            return ProviderResponse(
                canonical_model_id=model_id,
                provider_model_id=data.get("model", model_id),
                endpoint_id=f"ep-{self.provider_name}",
                text="".join(text_parts) if text_parts else None,
                tool_calls=tool_calls,
                finish_reason=finish_reason_val,
                usage=ProviderUsage(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    cached_tokens=cache_read,
                ),
                provider_request_id=resp.headers.get("request-id") or data.get("id"),
                total_latency_ms=total_latency_ms,
                raw_metadata={
                    "id": data.get("id"),
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                }
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(f"Timeout connecting to Anthropic API", provider_id=self.provider_name) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(f"Network error connecting to Anthropic API: {str(exc)}", provider_id=self.provider_name) from exc
        finally:
            if should_close:
                await client.aclose()

    async def stream(self, request: ProviderRequest, model_id: str = "claude-3-5-sonnet-20241022") -> AsyncIterator[ProviderStreamEvent]:
        """Executes a streaming completion call using Anthropic native SSE events."""
        url = f"{self.base_url}/messages"
        payload = self._build_messages_payload(request, model_id, stream=True)

        client = self._get_client()
        should_close = self._custom_client is None
        seq_num = 0

        try:
            async with client.stream("POST", url, json=payload, headers=self._build_headers()) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    raise self._map_http_error(resp.status_code, err_text.decode("utf-8", errors="replace"))

                buffer = ""
                event_type = ""
                
                async for chunk_bytes in resp.aiter_bytes():
                    buffer += chunk_bytes.decode("utf-8", errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                data = json.loads(data_str)
                            except Exception:
                                continue

                            seq_num += 1

                            if event_type == "content_block_delta":
                                delta_data = data.get("delta", {})
                                d_type = delta_data.get("type")
                                if d_type == "text_delta":
                                    yield ProviderStreamEvent(
                                        event_type="token",
                                        sequence_number=seq_num,
                                        delta=delta_data.get("text", "")
                                    )
                                elif d_type == "input_json_delta":
                                    yield ProviderStreamEvent(
                                        event_type="tool_call_delta",
                                        sequence_number=seq_num,
                                        tool_call_delta={"function": {"arguments": delta_data.get("partial_json", "")}}
                                    )
                            elif event_type == "message_stop":
                                yield ProviderStreamEvent(
                                    event_type="done",
                                    sequence_number=seq_num,
                                    finish_reason=FinishReason.STOP.value,
                                )
                                return

        except asyncio.CancelledError:
            raise CancellationFailure("Anthropic stream was cancelled", provider_id=self.provider_name)
        except httpx.TimeoutException as exc:
            raise TimeoutFailure("Timeout streaming from Anthropic API", provider_id=self.provider_name) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(f"Network error streaming from Anthropic API: {str(exc)}", provider_id=self.provider_name) from exc
        finally:
            if should_close:
                await client.aclose()

    async def list_models(self) -> List[DiscoveredModel]:
        """Queries Anthropic /v1/models endpoint."""
        url = f"{self.base_url}/models"
        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.get(url, headers=self._build_headers())
            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            raw_models = data.get("data", [])
            results = []
            for item in raw_models:
                m_id = item.get("id", "")
                results.append(
                    DiscoveredModel(
                        raw_model_id=m_id,
                        canonical_name=item.get("display_name", m_id),
                        provider_id=self.provider_name,
                        capabilities=["chat", "streaming", "tool_use", "vision", "prompt_caching"]
                    )
                )
            return results
        except httpx.TimeoutException as exc:
            raise TimeoutFailure("Timeout discovering models from Anthropic API", provider_id=self.provider_name) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(f"Network error discovering models from Anthropic API: {str(exc)}", provider_id=self.provider_name) from exc
        finally:
            if should_close:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        """Executes real diagnostic health probe call."""
        start_time = time.perf_counter()
        try:
            models = await self.list_models()
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
