"""
Native Ollama Provider Adapter for WindAgent Provider Subsystem V3.
Implements native Ollama API (POST /api/chat, GET /api/tags), tokens/sec metrics,
and local reachability probing without OpenAI compatibility wrappers.
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
    CancellationFailure,
    InvalidRequestFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    TimeoutFailure,
)
from windagent_providers.base.secret_redaction import redact_text


class OllamaProviderAdapter:
    """Native Ollama REST API Adapter."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        api_key: Optional[str] = None,
        timeout_seconds: float = 60.0,
        keep_alive: str = "5m",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = "ollama"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.keep_alive = keep_alive
        self._custom_client = http_client

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
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

    def _build_ollama_payload(
        self, request: ProviderRequest, model_id: str, stream: bool = False
    ) -> Dict[str, Any]:
        messages = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})

        for msg in request.messages:
            messages.append(
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            )

        options: Dict[str, Any] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.seed is not None:
            options["seed"] = request.seed
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if request.stop_sequences:
            options["stop"] = request.stop_sequences

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
        }

        if options:
            payload["options"] = options

        if request.tools:
            payload["tools"] = request.tools

        return payload

    def _map_http_error(self, status_code: int, body_text: str) -> ProviderFailure:
        clean_text = redact_text(body_text)
        try:
            err_json = json.loads(body_text)
            err_msg = redact_text(err_json.get("error", clean_text))
        except Exception:
            err_msg = clean_text

        if status_code == 404:
            return ModelNotFoundFailure(
                err_msg, provider_id=self.provider_name, status_code=status_code
            )
        elif status_code == 400:
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
        self, request: ProviderRequest, model_id: str = "llama3.1"
    ) -> ProviderResponse:
        """Executes a synchronous completion call using Ollama /api/chat."""
        start_time = time.perf_counter()
        url = f"{self.base_url}/api/chat"
        payload = self._build_ollama_payload(request, model_id, stream=False)

        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.post(url, json=payload, headers=self._build_headers())
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            message = data.get("message", {})
            text_content = message.get("content")
            raw_tools = message.get("tool_calls", [])

            tool_calls = [
                {
                    "id": f"call-ollama-{idx}",
                    "type": "function",
                    "function": tc.get("function", {}),
                }
                for idx, tc in enumerate(raw_tools)
            ]

            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
            eval_duration = data.get("eval_duration", 0)
            tokens_per_sec = (
                (completion_tokens / (eval_duration / 1e9))
                if eval_duration > 0
                else 0.0
            )

            return ProviderResponse(
                canonical_model_id=model_id,
                provider_model_id=data.get("model", model_id),
                endpoint_id=f"ep-{self.provider_name}",
                text=text_content,
                tool_calls=tool_calls,
                finish_reason=FinishReason.TOOL_CALLS.value
                if tool_calls
                else FinishReason.STOP.value,
                usage=ProviderUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ),
                total_latency_ms=total_latency_ms,
                raw_metadata={
                    "done_reason": data.get("done_reason"),
                    "eval_duration_ns": eval_duration,
                    "tokens_per_sec": round(tokens_per_sec, 2),
                },
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout connecting to Ollama server at {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error connecting to Ollama server at {self.base_url}: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def stream(
        self, request: ProviderRequest, model_id: str = "llama3.1"
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Executes a streaming completion call using Ollama /api/chat stream."""
        url = f"{self.base_url}/api/chat"
        payload = self._build_ollama_payload(request, model_id, stream=True)

        client = self._get_client()
        should_close = self._custom_client is None
        seq_num = 0

        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._build_headers()
            ) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    raise self._map_http_error(
                        resp.status_code, err_text.decode("utf-8", errors="replace")
                    )

                buffer = ""
                async for chunk_bytes in resp.aiter_bytes():
                    buffer += chunk_bytes.decode("utf-8", errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except Exception:
                            continue

                        seq_num += 1
                        msg = data.get("message", {})
                        delta_text = msg.get("content")
                        done = data.get("done", False)

                        if done:
                            eval_count = data.get("eval_count", 0)
                            prompt_count = data.get("prompt_eval_count", 0)
                            yield ProviderStreamEvent(
                                event_type="done",
                                sequence_number=seq_num,
                                finish_reason=FinishReason.STOP.value,
                                usage=ProviderUsage(
                                    prompt_tokens=prompt_count,
                                    completion_tokens=eval_count,
                                ),
                            )
                            return
                        else:
                            yield ProviderStreamEvent(
                                event_type="token",
                                sequence_number=seq_num,
                                delta=delta_text,
                            )

        except asyncio.CancelledError:
            raise CancellationFailure(
                "Ollama stream was cancelled", provider_id=self.provider_name
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                "Timeout streaming from Ollama server", provider_id=self.provider_name
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error streaming from Ollama server: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def list_models(self) -> List[DiscoveredModel]:
        """Queries Ollama /api/tags endpoint to discover installed models."""
        url = f"{self.base_url}/api/tags"
        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.get(url, headers=self._build_headers())
            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            models_raw = data.get("models", [])
            results = []
            for m in models_raw:
                name = m.get("name", "")
                results.append(
                    DiscoveredModel(
                        raw_model_id=name,
                        canonical_name=name,
                        provider_id=self.provider_name,
                        capabilities=["chat", "streaming", "tool_use"],
                    )
                )
            return results
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                f"Timeout discovering models from Ollama at {self.base_url}",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error discovering models from Ollama at {self.base_url}: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        """Executes diagnostic health probe network call."""
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
