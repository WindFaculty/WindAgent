"""
Native Google Gemini Provider Adapter for WindAgent Provider Subsystem V3.
Implements native generateContent API (POST /v1beta/models/{model}:generateContent),
functionDeclarations, inlineData multimodal parts, and safety ratings without OpenAI compatibility wrappers.
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
    InvalidRequestFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from windagent_providers.base.secret_redaction import redact_text


class GoogleGeminiProviderAdapter:
    """Native Google Gemini REST API Adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = "google"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._custom_client = http_client

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            # Auth via header, never the query string: httpx INFO logs the
            # request URL, so a ``?key=`` query parameter leaks the credential
            # into process logs and evidence tails.
            headers["x-goog-api-key"] = self.api_key
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client:
            return self._custom_client
        return httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    def _build_gemini_payload(self, request: ProviderRequest) -> Dict[str, Any]:
        contents = []
        for msg in request.messages:
            role = msg.get("role")
            if role == "system":
                continue
            gemini_role = "user" if role in ("user", "human") else "model"
            content_str = msg.get("content", "")
            contents.append(
                {"role": gemini_role, "parts": [{"text": str(content_str)}]}
            )

        # Canonical provider requests carry the single-turn user text in
        # ``prompt`` (RouteLockedModelPort sets messages=[]); without this the
        # API rejects the call with "contents is not specified".
        if not contents and (request.prompt or "").strip():
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        # Add image parts if provided
        if request.image_parts:
            for img in request.image_parts:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": img.get("mime_type", "image/png"),
                                    "data": img.get("data", ""),
                                }
                            }
                        ],
                    }
                )

        payload: Dict[str, Any] = {"contents": contents}

        if request.system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }

        gen_config: Dict[str, Any] = {}
        if request.temperature is not None:
            gen_config["temperature"] = request.temperature
        if request.top_p is not None:
            gen_config["topP"] = request.top_p
        if request.max_output_tokens is not None:
            gen_config["maxOutputTokens"] = request.max_output_tokens
        if request.stop_sequences:
            gen_config["stopSequences"] = request.stop_sequences
        if gen_config:
            payload["generationConfig"] = gen_config

        if request.tools:
            func_decls = []
            for t in request.tools:
                fn = t.get("function", t)
                func_decls.append(
                    {
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": fn.get(
                            "parameters", {"type": "OBJECT", "properties": {}}
                        ),
                    }
                )
            payload["tools"] = [{"functionDeclarations": func_decls}]

        return payload

    def _map_http_error(self, status_code: int, body_text: str) -> ProviderFailure:
        clean_text = redact_text(body_text)
        try:
            err_json = json.loads(body_text)
            err_msg = redact_text(err_json.get("error", {}).get("message", clean_text))
        except Exception:
            err_msg = clean_text

        if status_code in (401, 403):
            return AuthenticationFailure(
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
            if "safety" in err_msg.lower() or "blocked" in err_msg.lower():
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
        self, request: ProviderRequest, model_id: str = "gemini-1.5-pro"
    ) -> ProviderResponse:
        """Executes a synchronous completion call using Gemini generateContent API."""
        start_time = time.perf_counter()
        clean_model = model_id.replace("models/", "")
        url = f"{self.base_url}/models/{clean_model}:generateContent"
        payload = self._build_gemini_payload(request)

        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.post(url, json=payload, headers=self._build_headers())
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            candidates = data.get("candidates", [{}])
            first_cand = candidates[0] if candidates else {}

            parts = first_cand.get("content", {}).get("parts", [])
            text_parts = []
            tool_calls = []

            for pt in parts:
                if "text" in pt:
                    text_parts.append(pt["text"])
                elif "functionCall" in pt:
                    fc = pt["functionCall"]
                    tool_calls.append(
                        {
                            "id": f"call-{fc.get('name')}",
                            "type": "function",
                            "function": {
                                "name": fc.get("name"),
                                "arguments": json.dumps(fc.get("args", {})),
                            },
                        }
                    )

            finish_reason_raw = first_cand.get("finishReason", "STOP")
            finish_val = FinishReason.STOP.value
            if tool_calls:
                finish_val = FinishReason.TOOL_CALLS.value
            elif finish_reason_raw in ("SAFETY", "RECITATION"):
                finish_val = FinishReason.CONTENT_FILTER.value
            elif finish_reason_raw == "MAX_TOKENS":
                finish_val = FinishReason.LENGTH.value

            usage_meta = data.get("usageMetadata", {})
            prompt_tokens = usage_meta.get("promptTokenCount", 0)
            completion_tokens = usage_meta.get("candidatesTokenCount", 0)

            return ProviderResponse(
                canonical_model_id=clean_model,
                provider_model_id=clean_model,
                endpoint_id=f"ep-{self.provider_name}",
                text="".join(text_parts) if text_parts else None,
                tool_calls=tool_calls,
                finish_reason=finish_val,
                usage=ProviderUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ),
                total_latency_ms=total_latency_ms,
                raw_metadata={
                    "safetyRatings": first_cand.get("safetyRatings", []),
                    "finishReason": finish_reason_raw,
                },
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                "Timeout connecting to Google Gemini API",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error connecting to Google Gemini API: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def stream(
        self, request: ProviderRequest, model_id: str = "gemini-1.5-pro"
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Executes a streaming completion call using Gemini streamGenerateContent API."""
        clean_model = model_id.replace("models/", "")
        url = f"{self.base_url}/models/{clean_model}:streamGenerateContent"
        payload = self._build_gemini_payload(request)

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

                    try:
                        data = json.loads(buffer)
                        buffer = ""
                    except Exception:
                        continue

                    candidates = data.get("candidates", [{}])
                    first_cand = candidates[0] if candidates else {}
                    parts = first_cand.get("content", {}).get("parts", [])

                    for pt in parts:
                        seq_num += 1
                        if "text" in pt:
                            yield ProviderStreamEvent(
                                event_type="token",
                                sequence_number=seq_num,
                                delta=pt["text"],
                            )

                seq_num += 1
                yield ProviderStreamEvent(
                    event_type="done",
                    sequence_number=seq_num,
                    finish_reason=FinishReason.STOP.value,
                )
        except asyncio.CancelledError:
            raise CancellationFailure(
                "Gemini stream was cancelled", provider_id=self.provider_name
            )
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                "Timeout streaming from Google Gemini API",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error streaming from Google Gemini API: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def list_models(self) -> List[DiscoveredModel]:
        """Queries Google Gemini /v1beta/models endpoint."""
        url = f"{self.base_url}/models"
        client = self._get_client()
        should_close = self._custom_client is None

        try:
            resp = await client.get(url, headers=self._build_headers())
            if resp.status_code != 200:
                raise self._map_http_error(resp.status_code, resp.text)

            data = resp.json()
            raw_models = data.get("models", [])
            results = []
            for item in raw_models:
                m_name = item.get("name", "").replace("models/", "")
                caps = ["chat", "streaming", "tool_use", "vision"]
                # Live API models expose video input + live capabilities (Section 1: gemini-3.1-flash-live-preview)
                if "live" in m_name.lower():
                    caps.extend(["live_api", "video_input"])
                results.append(
                    DiscoveredModel(
                        raw_model_id=m_name,
                        canonical_name=item.get("displayName", m_name),
                        provider_id=self.provider_name,
                        context_window=item.get("inputTokenLimit", 1000000),
                        capabilities=caps,
                    )
                )
            return results
        except httpx.TimeoutException as exc:
            raise TimeoutFailure(
                "Timeout discovering models from Google Gemini API",
                provider_id=self.provider_name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkFailure(
                f"Network error discovering models from Google Gemini API: {str(exc)}",
                provider_id=self.provider_name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        """Executes real diagnostic health probe call."""
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
